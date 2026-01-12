"""
Date Range Energy Analysis Tool
Takes a date range and returns detailed TOU rate category breakdown
"""

import pandas as pd
from datetime import datetime
from typing import Dict, Tuple
from energy_usage import EnergyUsageParser
from rate_comparison import DukeEnergyRateCalculator
import pytz


class DateRangeAnalyzer:
    """Analyze energy usage and costs for a specific date range"""

    def __init__(self, xml_file_path: str, timezone: str = 'America/New_York'):
        """
        Initialize the analyzer

        Args:
            xml_file_path: Path to the Green Button XML file
            timezone: Timezone string (e.g., 'America/New_York', 'America/Chicago')
                     Defaults to 'America/New_York' for Duke Energy
        """
        self.parser = EnergyUsageParser(xml_file_path, timezone=timezone)
        self.calculator = DukeEnergyRateCalculator()
        self.energy_df = None
        self.timezone = timezone

    def load_data(self):
        """Load and parse the energy data"""
        self.parser.parse()
        self.energy_df = self.parser.to_dataframe()

    def analyze_date_range(self, start_date: str, end_date: str) -> Dict:
        """
        Analyze energy usage for a specific date range

        Args:
            start_date: Start date string (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            end_date: End date string (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)

        Returns:
            Dictionary with detailed analysis including:
            - Rate category breakdown (peak, off-peak, discount)
            - kWh used in each category
            - Electricity costs
            - Demand charges (for TOU rate)
        """
        if self.energy_df is None:
            self.load_data()

        # Convert string dates to timezone-aware timestamps
        tz = pytz.timezone(self.timezone)
        start = tz.localize(pd.to_datetime(start_date).to_pydatetime())
        end = tz.localize(pd.to_datetime(end_date).to_pydatetime())

        # Filter data for the date range
        mask = (self.energy_df.index >= start) & (self.energy_df.index <= end)
        range_df = self.energy_df[mask].copy()

        if len(range_df) == 0:
            raise ValueError(f"No data found for date range {start_date} to {end_date}")

        # Classify TOU periods
        range_df['tou_period'] = range_df.index.map(self.calculator._classify_tou_period)
        range_df['tou_ev_period'] = range_df.index.map(self.calculator._classify_tou_ev_period)

        # Calculate demand (kW) from kWh (assumes 30-minute intervals)
        range_df['demand_kw'] = range_df['value'] / 0.5

        # Get season info
        season = self.calculator._get_season(start.month)

        # ======================
        # TOU (R-TOUD) Analysis
        # ======================

        # Energy by TOU period
        on_peak_kwh = range_df[range_df['tou_period'] == 'on_peak']['value'].sum()
        off_peak_kwh = range_df[range_df['tou_period'] == 'off_peak']['value'].sum()
        discount_kwh = range_df[range_df['tou_period'] == 'discount']['value'].sum()
        total_kwh = on_peak_kwh + off_peak_kwh + discount_kwh

        # Energy costs
        on_peak_cost = on_peak_kwh * self.calculator.tou_rates['energy_rates']['on_peak']
        off_peak_cost = off_peak_kwh * self.calculator.tou_rates['energy_rates']['off_peak']
        discount_cost = discount_kwh * self.calculator.tou_rates['energy_rates']['discount']
        total_energy_cost = on_peak_cost + off_peak_cost + discount_cost

        # Demand charges
        on_peak_data = range_df[range_df['tou_period'] == 'on_peak']
        on_peak_demand_kw = on_peak_data['demand_kw'].max() if len(on_peak_data) > 0 else 0
        max_demand_kw = range_df['demand_kw'].max()

        demand_charge_onpeak = on_peak_demand_kw * self.calculator.tou_rates['demand_charge_onpeak']
        demand_charge_max = max_demand_kw * self.calculator.tou_rates['demand_charge_max']
        total_demand_charge = demand_charge_onpeak + demand_charge_max

        # Total TOU cost
        total_tou_cost = total_energy_cost + total_demand_charge

        # ======================
        # TOU-EV Analysis
        # ======================

        ev_discount_kwh = range_df[range_df['tou_ev_period'] == 'discount']['value'].sum()
        ev_standard_kwh = range_df[range_df['tou_ev_period'] == 'standard']['value'].sum()

        ev_discount_cost = ev_discount_kwh * self.calculator.tou_ev_rates['energy_rates']['discount']
        ev_standard_cost = ev_standard_kwh * self.calculator.tou_ev_rates['energy_rates']['standard']
        total_ev_cost = ev_discount_cost + ev_standard_cost

        # ======================
        # Standard Rate Analysis
        # ======================

        if season == 'summer':
            standard_cost = total_kwh * self.calculator.standard_rates['summer']['energy_rate']
        else:  # winter
            tier_threshold = self.calculator.standard_rates['winter']['tier_threshold']
            if total_kwh <= tier_threshold:
                standard_cost = total_kwh * self.calculator.standard_rates['winter']['energy_rate_tier1']
            else:
                standard_cost = (tier_threshold * self.calculator.standard_rates['winter']['energy_rate_tier1'] +
                               (total_kwh - tier_threshold) * self.calculator.standard_rates['winter']['energy_rate_tier2'])

        # Return comprehensive analysis
        return {
            'date_range': {
                'start': start,
                'end': end,
                'season': season,
                'num_readings': len(range_df)
            },
            'total_usage': {
                'total_kwh': total_kwh
            },
            'tou_rate': {
                'on_peak': {
                    'kwh': on_peak_kwh,
                    'percentage': (on_peak_kwh / total_kwh * 100) if total_kwh > 0 else 0,
                    'cost': on_peak_cost,
                    'rate_cents_per_kwh': self.calculator.tou_rates['energy_rates']['on_peak'] * 100
                },
                'off_peak': {
                    'kwh': off_peak_kwh,
                    'percentage': (off_peak_kwh / total_kwh * 100) if total_kwh > 0 else 0,
                    'cost': off_peak_cost,
                    'rate_cents_per_kwh': self.calculator.tou_rates['energy_rates']['off_peak'] * 100
                },
                'discount': {
                    'kwh': discount_kwh,
                    'percentage': (discount_kwh / total_kwh * 100) if total_kwh > 0 else 0,
                    'cost': discount_cost,
                    'rate_cents_per_kwh': self.calculator.tou_rates['energy_rates']['discount'] * 100
                },
                'demand_charges': {
                    'on_peak_demand_kw': on_peak_demand_kw,
                    'max_demand_kw': max_demand_kw,
                    'on_peak_demand_charge': demand_charge_onpeak,
                    'max_demand_charge': demand_charge_max,
                    'total_demand_charge': total_demand_charge
                },
                'total_energy_cost': total_energy_cost,
                'total_cost': total_tou_cost
            },
            'tou_ev_rate': {
                'discount': {
                    'kwh': ev_discount_kwh,
                    'percentage': (ev_discount_kwh / total_kwh * 100) if total_kwh > 0 else 0,
                    'cost': ev_discount_cost,
                    'rate_cents_per_kwh': self.calculator.tou_ev_rates['energy_rates']['discount'] * 100,
                    'hours': '11 PM - 5 AM'
                },
                'standard': {
                    'kwh': ev_standard_kwh,
                    'percentage': (ev_standard_kwh / total_kwh * 100) if total_kwh > 0 else 0,
                    'cost': ev_standard_cost,
                    'rate_cents_per_kwh': self.calculator.tou_ev_rates['energy_rates']['standard'] * 100,
                    'hours': 'All other hours'
                },
                'total_cost': total_ev_cost
            },
            'standard_rate': {
                'total_cost': standard_cost
            },
            'comparison': {
                'cheapest_rate': min([
                    ('Standard', standard_cost),
                    ('TOU', total_tou_cost),
                    ('TOU-EV', total_ev_cost)
                ], key=lambda x: x[1])[0],
                'tou_vs_standard_savings': standard_cost - total_tou_cost,
                'tou_ev_vs_standard_savings': standard_cost - total_ev_cost,
                'tou_ev_vs_tou_savings': total_tou_cost - total_ev_cost
            }
        }

    def print_analysis(self, analysis: Dict):
        """
        Print formatted analysis results

        Args:
            analysis: Dictionary returned from analyze_date_range()
        """
        dr = analysis['date_range']
        total = analysis['total_usage']
        tou = analysis['tou_rate']
        tou_ev = analysis['tou_ev_rate']
        std = analysis['standard_rate']
        comp = analysis['comparison']

        print("\n" + "=" * 80)
        print("DATE RANGE ENERGY ANALYSIS")
        print("=" * 80)

        print(f"\nDate Range: {dr['start'].strftime('%Y-%m-%d %H:%M')} to {dr['end'].strftime('%Y-%m-%d %H:%M')}")
        print(f"Season: {dr['season'].capitalize()}")
        print(f"Number of readings: {dr['num_readings']:,}")
        print(f"Total usage: {total['total_kwh']:.2f} kWh")

        print("\n" + "-" * 80)
        print("TOU RATE (R-TOUD) - Time-of-Use with Demand Charges")
        print("-" * 80)

        print("\nENERGY USAGE BY PERIOD:")
        print(f"  On-Peak:      {tou['on_peak']['kwh']:>10.2f} kWh ({tou['on_peak']['percentage']:>5.1f}%) "
              f"@ {tou['on_peak']['rate_cents_per_kwh']:.3f}¢/kWh  = ${tou['on_peak']['cost']:>8.2f}")
        print(f"  Off-Peak:     {tou['off_peak']['kwh']:>10.2f} kWh ({tou['off_peak']['percentage']:>5.1f}%) "
              f"@ {tou['off_peak']['rate_cents_per_kwh']:.3f}¢/kWh  = ${tou['off_peak']['cost']:>8.2f}")
        print(f"  Discount:     {tou['discount']['kwh']:>10.2f} kWh ({tou['discount']['percentage']:>5.1f}%) "
              f"@ {tou['discount']['rate_cents_per_kwh']:.3f}¢/kWh  = ${tou['discount']['cost']:>8.2f}")
        print(f"  {'─' * 75}")
        print(f"  Total Energy: {total['total_kwh']:>10.2f} kWh                      = ${tou['total_energy_cost']:>8.2f}")

        print("\nDEMAND CHARGES:")
        print(f"  On-Peak Demand:  {tou['demand_charges']['on_peak_demand_kw']:>6.2f} kW @ $1.99/kW  = ${tou['demand_charges']['on_peak_demand_charge']:>8.2f}")
        print(f"  Max Demand:      {tou['demand_charges']['max_demand_kw']:>6.2f} kW @ $3.91/kW  = ${tou['demand_charges']['max_demand_charge']:>8.2f}")
        print(f"  {'─' * 75}")
        print(f"  Total Demand Charges:                          = ${tou['demand_charges']['total_demand_charge']:>8.2f}")

        print(f"\nTOTAL TOU COST: ${tou['total_cost']:.2f}")

        print("\n" + "-" * 80)
        print("TOU-EV RATE (R-TOU-EV) - Simplified TOU for EV Owners, No Demand Charges")
        print("-" * 80)

        print("\nENERGY USAGE BY PERIOD:")
        print(f"  Discount:     {tou_ev['discount']['kwh']:>10.2f} kWh ({tou_ev['discount']['percentage']:>5.1f}%) "
              f"@ {tou_ev['discount']['rate_cents_per_kwh']:.3f}¢/kWh  = ${tou_ev['discount']['cost']:>8.2f}")
        print(f"                {tou_ev['discount']['hours']}")
        print(f"  Standard:     {tou_ev['standard']['kwh']:>10.2f} kWh ({tou_ev['standard']['percentage']:>5.1f}%) "
              f"@ {tou_ev['standard']['rate_cents_per_kwh']:.3f}¢/kWh  = ${tou_ev['standard']['cost']:>8.2f}")
        print(f"                {tou_ev['standard']['hours']}")
        print(f"  {'─' * 75}")
        print(f"  Total:        {total['total_kwh']:>10.2f} kWh                      = ${tou_ev['total_cost']:>8.2f}")

        print(f"\nTOTAL TOU-EV COST: ${tou_ev['total_cost']:.2f} (NO DEMAND CHARGES)")

        print("\n" + "-" * 80)
        print("STANDARD RATE (RES)")
        print("-" * 80)
        print(f"\nTotal Cost: ${std['total_cost']:.2f}")

        print("\n" + "-" * 80)
        print("COST COMPARISON")
        print("-" * 80)

        print(f"\nStandard Rate:  ${std['total_cost']:>10.2f}")
        print(f"TOU Rate:       ${tou['total_cost']:>10.2f}  (${comp['tou_vs_standard_savings']:+.2f})")
        print(f"TOU-EV Rate:    ${tou_ev['total_cost']:>10.2f}  (${comp['tou_ev_vs_standard_savings']:+.2f})")

        print(f"\n★ CHEAPEST RATE: {comp['cheapest_rate']}")

        if comp['cheapest_rate'] == 'TOU-EV':
            print(f"\nTOU-EV saves ${comp['tou_ev_vs_standard_savings']:.2f} vs Standard")
            print(f"TOU-EV saves ${comp['tou_ev_vs_tou_savings']:.2f} vs TOU (avoids demand charges)")
        elif comp['cheapest_rate'] == 'TOU':
            print(f"\nTOU saves ${comp['tou_vs_standard_savings']:.2f} vs Standard")

        print("\n" + "=" * 80)


def main():
    """Example usage"""
    import sys

    if len(sys.argv) < 3:
        print("Usage: python date_range_analyzer.py <start_date> <end_date> [xml_file]")
        print("\nExamples:")
        print('  python date_range_analyzer.py "2024-01-01" "2024-01-31"')
        print('  python date_range_analyzer.py "2024-06-15" "2024-06-21" "mydata.xml"')
        print('  python date_range_analyzer.py "2024-12-01 00:00:00" "2024-12-07 23:59:59"')
        sys.exit(1)

    start_date = sys.argv[1]
    end_date = sys.argv[2]
    xml_file = sys.argv[3] if len(sys.argv) > 3 else "Energy Usage.xml"

    print(f"Loading data from {xml_file}...")
    analyzer = DateRangeAnalyzer(xml_file)
    analyzer.load_data()

    print(f"Analyzing date range: {start_date} to {end_date}...")
    analysis = analyzer.analyze_date_range(start_date, end_date)

    analyzer.print_analysis(analysis)

    # Return the analysis dict for programmatic use
    return analysis


if __name__ == "__main__":
    main()
