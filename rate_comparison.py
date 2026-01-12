"""
Duke Energy Rate Comparison Tool
Compares costs between Standard Residential (RES) and Time-of-Use (R-TOUD) rate schedules
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime
from typing import Dict, Tuple
from energy_usage import EnergyUsageParser


class DukeEnergyRateCalculator:
    """Calculate electricity costs under Duke Energy Progress NC rate schedules"""

    def __init__(self):
        """Initialize rate structures (effective October 1, 2025)"""

        # Standard Residential Service (Schedule RES)
        self.standard_rates = {
            'customer_charge': 14.00,
            'summer': {  # May - September
                'energy_rate': 0.12623  # ¢/kWh for all kWh
            },
            'winter': {  # October - April
                'energy_rate_tier1': 0.12623,  # first 800 kWh
                'energy_rate_tier2': 0.11623,  # additional kWh
                'tier_threshold': 800
            }
        }

        # Time-of-Use Residential Service (Schedule R-TOUD)
        self.tou_rates = {
            'customer_charge': 14.00,
            'demand_charge_onpeak': 1.99,  # $/kW
            'demand_charge_max': 3.91,     # $/kW
            'energy_rates': {
                'on_peak': 0.15638,    # ¢/kWh
                'off_peak': 0.06633,   # ¢/kWh
                'discount': 0.04347    # ¢/kWh
            }
        }

        # Time-of-Use with EV Charging (Schedule R-TOU-EV)
        # Effective January 1, 2026 - Pilot program for EV owners
        self.tou_ev_rates = {
            'customer_charge': 14.00,
            'energy_rates': {
                'discount': 0.06548,   # ¢/kWh (11 PM - 5 AM)
                'standard': 0.13096    # ¢/kWh (all other hours)
            }
        }

        # TOU period definitions (Eastern Prevailing Time)
        self.tou_periods = {
            'summer': {  # May - September
                'on_peak': {
                    'days': [0, 1, 2, 3, 4],  # Monday-Friday (excluding holidays)
                    'hours': list(range(18, 21))  # 6:00 PM - 9:00 PM
                },
                'discount': {
                    'hours': list(range(1, 6))  # 1:00 AM - 6:00 AM
                }
            },
            'winter': {  # October - April
                'on_peak': {
                    'days': [0, 1, 2, 3, 4],  # Monday-Friday (excluding holidays)
                    'hours': list(range(6, 9))  # 6:00 AM - 9:00 AM
                },
                'discount': {
                    'hours': list(range(1, 3)) + list(range(11, 16))  # 1:00-3:00 AM, 11:00 AM-4:00 PM
                }
            }
        }

        # Holidays (when TOU on-peak doesn't apply)
        self.holidays = [
            # New Year's Day, Good Friday, Memorial Day, Independence Day,
            # Labor Day, Thanksgiving, Day after Thanksgiving, Christmas
            # Note: These would need to be defined for specific years
        ]

    def _get_season(self, month: int) -> str:
        """Determine season from month"""
        if month in [5, 6, 7, 8, 9]:
            return 'summer'
        else:
            return 'winter'

    def _classify_tou_period(self, timestamp: pd.Timestamp) -> str:
        """
        Classify a timestamp into TOU period (on-peak, off-peak, or discount)

        Args:
            timestamp: pandas Timestamp

        Returns:
            'on_peak', 'off_peak', or 'discount'
        """
        season = self._get_season(timestamp.month)
        hour = timestamp.hour
        day_of_week = timestamp.dayofweek

        # Check if it's a holiday (simplified - would need full holiday logic)
        # is_holiday = timestamp.date() in self.holidays
        is_holiday = False

        # Discount period (applies all days including holidays)
        if hour in self.tou_periods[season]['discount']['hours']:
            return 'discount'

        # On-peak period (Monday-Friday, excluding holidays)
        if not is_holiday and day_of_week in self.tou_periods[season]['on_peak']['days']:
            if hour in self.tou_periods[season]['on_peak']['hours']:
                return 'on_peak'

        # Everything else is off-peak
        return 'off_peak'

    def _classify_tou_ev_period(self, timestamp: pd.Timestamp) -> str:
        """
        Classify a timestamp into TOU-EV period (discount or standard)

        Args:
            timestamp: pandas Timestamp

        Returns:
            'discount' or 'standard'
        """
        hour = timestamp.hour

        # Discount period: 11 PM - 5 AM (23:00 - 05:00)
        # Hours 23, 0, 1, 2, 3, 4 (hour 5 starts the standard period)
        if hour >= 23 or hour < 5:
            return 'discount'
        else:
            return 'standard'

    def calculate_standard_cost(self, energy_df: pd.DataFrame) -> Dict:
        """
        Calculate monthly cost under Standard Residential (RES) rate

        Args:
            energy_df: DataFrame with datetime index and 'value' column (kWh per interval)

        Returns:
            Dictionary with cost breakdown by month
        """
        monthly_costs = []

        # Group by month
        for month_date, month_data in energy_df.groupby(pd.Grouper(freq='M')):
            month = month_date.month
            season = self._get_season(month)
            total_kwh = month_data['value'].sum()

            # Customer charge
            customer_charge = self.standard_rates['customer_charge']

            # Energy charge
            if season == 'summer':
                energy_charge = total_kwh * self.standard_rates['summer']['energy_rate']
            else:  # winter
                tier_threshold = self.standard_rates['winter']['tier_threshold']
                if total_kwh <= tier_threshold:
                    energy_charge = total_kwh * self.standard_rates['winter']['energy_rate_tier1']
                else:
                    energy_charge = (tier_threshold * self.standard_rates['winter']['energy_rate_tier1'] +
                                   (total_kwh - tier_threshold) * self.standard_rates['winter']['energy_rate_tier2'])

            total_cost = customer_charge + energy_charge

            monthly_costs.append({
                'month': month_date,
                'season': season,
                'kwh_total': total_kwh,
                'customer_charge': customer_charge,
                'energy_charge': energy_charge,
                'total_cost': total_cost
            })

        return pd.DataFrame(monthly_costs)

    def calculate_tou_cost(self, energy_df: pd.DataFrame) -> Dict:
        """
        Calculate monthly cost under Time-of-Use (R-TOUD) rate

        Args:
            energy_df: DataFrame with datetime index and 'value' column (kWh per interval)

        Returns:
            Dictionary with cost breakdown by month
        """
        # Classify each reading by TOU period
        energy_df = energy_df.copy()
        energy_df['tou_period'] = energy_df.index.map(self._classify_tou_period)

        # Assume 30-minute intervals, convert kWh to kW demand
        # For demand: kW = (kWh / 0.5 hours)
        energy_df['demand_kw'] = energy_df['value'] / 0.5

        monthly_costs = []

        # Group by month
        for month_date, month_data in energy_df.groupby(pd.Grouper(freq='M')):
            month = month_date.month
            season = self._get_season(month)

            # Customer charge
            customer_charge = self.tou_rates['customer_charge']

            # Demand charges
            on_peak_data = month_data[month_data['tou_period'] == 'on_peak']
            on_peak_demand_kw = on_peak_data['demand_kw'].max() if len(on_peak_data) > 0 else 0
            max_demand_kw = month_data['demand_kw'].max()

            demand_charge_onpeak = on_peak_demand_kw * self.tou_rates['demand_charge_onpeak']
            demand_charge_max = max_demand_kw * self.tou_rates['demand_charge_max']
            total_demand_charge = demand_charge_onpeak + demand_charge_max

            # Energy charges by period
            on_peak_kwh = month_data[month_data['tou_period'] == 'on_peak']['value'].sum()
            off_peak_kwh = month_data[month_data['tou_period'] == 'off_peak']['value'].sum()
            discount_kwh = month_data[month_data['tou_period'] == 'discount']['value'].sum()

            on_peak_charge = on_peak_kwh * self.tou_rates['energy_rates']['on_peak']
            off_peak_charge = off_peak_kwh * self.tou_rates['energy_rates']['off_peak']
            discount_charge = discount_kwh * self.tou_rates['energy_rates']['discount']

            total_energy_charge = on_peak_charge + off_peak_charge + discount_charge
            total_cost = customer_charge + total_demand_charge + total_energy_charge

            monthly_costs.append({
                'month': month_date,
                'season': season,
                'customer_charge': customer_charge,
                'on_peak_demand_kw': on_peak_demand_kw,
                'max_demand_kw': max_demand_kw,
                'demand_charge': total_demand_charge,
                'on_peak_kwh': on_peak_kwh,
                'off_peak_kwh': off_peak_kwh,
                'discount_kwh': discount_kwh,
                'on_peak_charge': on_peak_charge,
                'off_peak_charge': off_peak_charge,
                'discount_charge': discount_charge,
                'energy_charge': total_energy_charge,
                'total_cost': total_cost
            })

        return pd.DataFrame(monthly_costs)

    def calculate_tou_ev_cost(self, energy_df: pd.DataFrame) -> Dict:
        """
        Calculate monthly cost under Time-of-Use EV (R-TOU-EV) rate

        Args:
            energy_df: DataFrame with datetime index and 'value' column (kWh per interval)

        Returns:
            Dictionary with cost breakdown by month
        """
        # Classify each reading by TOU-EV period
        energy_df = energy_df.copy()
        energy_df['tou_ev_period'] = energy_df.index.map(self._classify_tou_ev_period)

        monthly_costs = []

        # Group by month
        for month_date, month_data in energy_df.groupby(pd.Grouper(freq='M')):
            month = month_date.month
            season = self._get_season(month)

            # Customer charge
            customer_charge = self.tou_ev_rates['customer_charge']

            # Energy charges by period (no demand charges for EV rate!)
            discount_kwh = month_data[month_data['tou_ev_period'] == 'discount']['value'].sum()
            standard_kwh = month_data[month_data['tou_ev_period'] == 'standard']['value'].sum()

            discount_charge = discount_kwh * self.tou_ev_rates['energy_rates']['discount']
            standard_charge = standard_kwh * self.tou_ev_rates['energy_rates']['standard']

            total_energy_charge = discount_charge + standard_charge
            total_cost = customer_charge + total_energy_charge

            monthly_costs.append({
                'month': month_date,
                'season': season,
                'customer_charge': customer_charge,
                'discount_kwh': discount_kwh,
                'standard_kwh': standard_kwh,
                'discount_charge': discount_charge,
                'standard_charge': standard_charge,
                'energy_charge': total_energy_charge,
                'total_cost': total_cost
            })

        return pd.DataFrame(monthly_costs)

    def compare_rates(self, energy_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Compare costs between Standard, TOU, and TOU-EV rates

        Args:
            energy_df: DataFrame with datetime index and 'value' column

        Returns:
            Tuple of (standard_costs, tou_costs, tou_ev_costs, comparison_df, comparison_all_df)
        """
        standard_costs = self.calculate_standard_cost(energy_df)
        tou_costs = self.calculate_tou_cost(energy_df)
        tou_ev_costs = self.calculate_tou_ev_cost(energy_df)

        # Create comparison DataFrame (original: Standard vs TOU)
        comparison = pd.DataFrame({
            'month': standard_costs['month'],
            'standard_cost': standard_costs['total_cost'],
            'tou_cost': tou_costs['total_cost'],
            'savings': standard_costs['total_cost'] - tou_costs['total_cost'],
            'savings_pct': ((standard_costs['total_cost'] - tou_costs['total_cost']) /
                           standard_costs['total_cost'] * 100)
        })

        # Create comprehensive comparison DataFrame (all three rates)
        comparison_all = pd.DataFrame({
            'month': standard_costs['month'],
            'standard_cost': standard_costs['total_cost'],
            'tou_cost': tou_costs['total_cost'],
            'tou_ev_cost': tou_ev_costs['total_cost'],
            'tou_savings': standard_costs['total_cost'] - tou_costs['total_cost'],
            'tou_ev_savings': standard_costs['total_cost'] - tou_ev_costs['total_cost'],
            'tou_ev_vs_tou_savings': tou_costs['total_cost'] - tou_ev_costs['total_cost']
        })

        return standard_costs, tou_costs, tou_ev_costs, comparison, comparison_all

    def plot_rate_comparison(self, comparison_df: pd.DataFrame, save_path: str = None):
        """
        Create visualization comparing rate costs

        Args:
            comparison_df: DataFrame from compare_rates()
            save_path: Optional path to save plot
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        # Plot 1: Monthly costs comparison
        ax1.plot(comparison_df['month'], comparison_df['standard_cost'],
                marker='o', linewidth=2, markersize=6, label='Standard Rate (RES)', color='#2E86AB')
        ax1.plot(comparison_df['month'], comparison_df['tou_cost'],
                marker='s', linewidth=2, markersize=6, label='Time-of-Use (R-TOUD)', color='#E63946')

        ax1.set_xlabel('Month', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Monthly Cost ($)', fontsize=12, fontweight='bold')
        ax1.set_title('Duke Energy Rate Comparison: Standard vs Time-of-Use',
                     fontsize=14, fontweight='bold', pad=20)
        ax1.legend(loc='best', fontsize=11)
        ax1.grid(True, alpha=0.3)

        # Plot 2: Monthly savings
        colors = ['green' if s > 0 else 'red' for s in comparison_df['savings']]
        ax2.bar(comparison_df['month'], comparison_df['savings'], color=colors, alpha=0.7)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)

        ax2.set_xlabel('Month', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Monthly Savings ($)', fontsize=12, fontweight='bold')
        ax2.set_title('Potential Savings with Time-of-Use Rate (Positive = TOU Saves Money)',
                     fontsize=14, fontweight='bold', pad=20)
        ax2.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        plt.show()

        return fig, (ax1, ax2)

    def plot_all_rates_comparison(self, comparison_all_df: pd.DataFrame, save_path: str = None):
        """
        Create visualization comparing all three rate options

        Args:
            comparison_all_df: Comprehensive comparison DataFrame
            save_path: Optional path to save plot
        """
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 10))

        # Plot 1: Monthly costs comparison for all three rates
        ax1.plot(comparison_all_df['month'], comparison_all_df['standard_cost'],
                marker='o', linewidth=2, markersize=6, label='Standard Rate (RES)', color='#2E86AB')
        ax1.plot(comparison_all_df['month'], comparison_all_df['tou_cost'],
                marker='s', linewidth=2, markersize=6, label='Time-of-Use (R-TOUD)', color='#E63946')
        ax1.plot(comparison_all_df['month'], comparison_all_df['tou_ev_cost'],
                marker='^', linewidth=2, markersize=6, label='TOU-EV (R-TOU-EV)', color='#06A77D')

        ax1.set_xlabel('Month', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Monthly Cost ($)', fontsize=12, fontweight='bold')
        ax1.set_title('Duke Energy Rate Comparison: All Three Rate Schedules',
                     fontsize=14, fontweight='bold', pad=20)
        ax1.legend(loc='best', fontsize=11)
        ax1.grid(True, alpha=0.3)

        # Plot 2: Monthly savings comparison (relative to Standard rate)
        width = 8  # Width of bars in days
        ax2.bar(comparison_all_df['month'], comparison_all_df['tou_savings'],
                width=width, label='TOU Savings', color='#E63946', alpha=0.7)
        ax2.bar(comparison_all_df['month'] + pd.Timedelta(days=width), comparison_all_df['tou_ev_savings'],
                width=width, label='TOU-EV Savings', color='#06A77D', alpha=0.7)
        ax2.axhline(y=0, color='black', linestyle='-', linewidth=0.5)

        ax2.set_xlabel('Month', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Monthly Savings vs Standard ($)', fontsize=12, fontweight='bold')
        ax2.set_title('Savings Comparison vs Standard Rate (Positive = Saves Money)',
                     fontsize=14, fontweight='bold', pad=20)
        ax2.legend(loc='best', fontsize=11)
        ax2.grid(True, alpha=0.3, axis='y')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        plt.show()

        return fig, (ax1, ax2)

    def print_comparison_summary(self, standard_costs: pd.DataFrame,
                                tou_costs: pd.DataFrame, comparison_df: pd.DataFrame):
        """Print detailed comparison summary"""

        print("\n" + "=" * 80)
        print("DUKE ENERGY PROGRESS NC - RATE COMPARISON SUMMARY")
        print("=" * 80)

        total_standard = standard_costs['total_cost'].sum()
        total_tou = tou_costs['total_cost'].sum()
        total_savings = total_standard - total_tou
        pct_savings = (total_savings / total_standard * 100) if total_standard > 0 else 0

        print(f"\nTOTAL ANNUAL COSTS:")
        print(f"  Standard Rate (Schedule RES):        ${total_standard:,.2f}")
        print(f"  Time-of-Use Rate (Schedule R-TOUD):  ${total_tou:,.2f}")
        print(f"  Annual Savings with TOU:             ${total_savings:,.2f} ({pct_savings:+.1f}%)")

        if total_savings > 0:
            print(f"\n  ✓ Time-of-Use rate saves ${total_savings:.2f} per year!")
        else:
            print(f"\n  ⚠ Standard rate is cheaper by ${abs(total_savings):.2f} per year")

        print("\n" + "-" * 80)
        print("MONTHLY BREAKDOWN:")
        print("-" * 80)
        print(f"{'Month':<12} {'Standard':<12} {'TOU':<12} {'Savings':<12} {'% Savings':<12}")
        print("-" * 80)

        for _, row in comparison_df.iterrows():
            month_str = row['month'].strftime('%Y-%m')
            print(f"{month_str:<12} ${row['standard_cost']:>10.2f} ${row['tou_cost']:>10.2f} "
                  f"${row['savings']:>10.2f} {row['savings_pct']:>10.1f}%")

        print("\n" + "-" * 80)
        print("AVERAGE TOU USAGE BREAKDOWN:")
        print("-" * 80)

        avg_on_peak = tou_costs['on_peak_kwh'].mean()
        avg_off_peak = tou_costs['off_peak_kwh'].mean()
        avg_discount = tou_costs['discount_kwh'].mean()
        total_avg = avg_on_peak + avg_off_peak + avg_discount

        print(f"  On-Peak:      {avg_on_peak:>8.1f} kWh ({avg_on_peak/total_avg*100:>5.1f}%)")
        print(f"  Off-Peak:     {avg_off_peak:>8.1f} kWh ({avg_off_peak/total_avg*100:>5.1f}%)")
        print(f"  Discount:     {avg_discount:>8.1f} kWh ({avg_discount/total_avg*100:>5.1f}%)")
        print(f"  Total:        {total_avg:>8.1f} kWh")

        print("\n" + "-" * 80)
        print("RECOMMENDATIONS:")
        print("-" * 80)

        on_peak_pct = (avg_on_peak / total_avg * 100) if total_avg > 0 else 0

        if total_savings > 0:
            print("  ✓ Time-of-Use rate is recommended for your usage pattern")
            if on_peak_pct < 15:
                print(f"  ✓ You're doing great! Only {on_peak_pct:.1f}% of usage during expensive on-peak hours")
            else:
                print(f"  ⚠ {on_peak_pct:.1f}% of usage is during on-peak - consider shifting more to off-peak")
        else:
            print("  • Standard rate is currently cheaper for your usage pattern")
            print(f"  • You use {on_peak_pct:.1f}% during on-peak hours")
            print("  • To benefit from TOU, try to:")
            print("    - Shift more usage to discount hours (1-6 AM in summer, 1-3 AM & 11 AM-4 PM in winter)")
            print("    - Avoid on-peak hours (6-9 PM summer, 6-9 AM winter on weekdays)")

        print("\n" + "=" * 80)

    def print_all_rates_summary(self, standard_costs: pd.DataFrame, tou_costs: pd.DataFrame,
                               tou_ev_costs: pd.DataFrame, comparison_all_df: pd.DataFrame):
        """Print comprehensive comparison summary for all three rates"""

        print("\n" + "=" * 80)
        print("DUKE ENERGY PROGRESS NC - COMPREHENSIVE RATE COMPARISON")
        print("All Three Rate Schedules: Standard (RES), TOU (R-TOUD), TOU-EV (R-TOU-EV)")
        print("=" * 80)

        total_standard = standard_costs['total_cost'].sum()
        total_tou = tou_costs['total_cost'].sum()
        total_tou_ev = tou_ev_costs['total_cost'].sum()

        tou_savings = total_standard - total_tou
        tou_ev_savings = total_standard - total_tou_ev
        tou_ev_vs_tou_savings = total_tou - total_tou_ev

        tou_pct = (tou_savings / total_standard * 100) if total_standard > 0 else 0
        tou_ev_pct = (tou_ev_savings / total_standard * 100) if total_standard > 0 else 0

        print(f"\nTOTAL ANNUAL COSTS:")
        print(f"  Standard Rate (RES):          ${total_standard:>10.2f}")
        print(f"  Time-of-Use Rate (R-TOUD):    ${total_tou:>10.2f}  (saves ${tou_savings:>7.2f}, {tou_pct:>5.1f}%)")
        print(f"  TOU-EV Rate (R-TOU-EV):       ${total_tou_ev:>10.2f}  (saves ${tou_ev_savings:>7.2f}, {tou_ev_pct:>5.1f}%)")

        print(f"\n  TOU-EV vs TOU savings:        ${tou_ev_vs_tou_savings:>10.2f}")

        # Determine best rate
        best_rate = min(
            ('Standard', total_standard),
            ('TOU', total_tou),
            ('TOU-EV', total_tou_ev),
            key=lambda x: x[1]
        )

        print(f"\n  ★ BEST RATE: {best_rate[0]} at ${best_rate[1]:,.2f}/year")

        print("\n" + "-" * 80)
        print("MONTHLY BREAKDOWN:")
        print("-" * 80)
        print(f"{'Month':<12} {'Standard':<12} {'TOU':<12} {'TOU-EV':<12} {'Best Rate':<12}")
        print("-" * 80)

        for _, row in comparison_all_df.iterrows():
            month_str = row['month'].strftime('%Y-%m')
            best = min(
                ('Std', row['standard_cost']),
                ('TOU', row['tou_cost']),
                ('EV', row['tou_ev_cost']),
                key=lambda x: x[1]
            )
            print(f"{month_str:<12} ${row['standard_cost']:>10.2f} ${row['tou_cost']:>10.2f} "
                  f"${row['tou_ev_cost']:>10.2f} {best[0]:<12}")

        print("\n" + "-" * 80)
        print("USAGE BREAKDOWN BY RATE SCHEDULE:")
        print("-" * 80)

        # TOU breakdown
        avg_on_peak = tou_costs['on_peak_kwh'].mean()
        avg_off_peak = tou_costs['off_peak_kwh'].mean()
        avg_discount = tou_costs['discount_kwh'].mean()
        total_avg = avg_on_peak + avg_off_peak + avg_discount

        print(f"\nR-TOUD (Complex TOU with demand charges):")
        print(f"  On-Peak:      {avg_on_peak:>8.1f} kWh ({avg_on_peak/total_avg*100:>5.1f}%) @ 15.638¢/kWh")
        print(f"  Off-Peak:     {avg_off_peak:>8.1f} kWh ({avg_off_peak/total_avg*100:>5.1f}%) @ 6.633¢/kWh")
        print(f"  Discount:     {avg_discount:>8.1f} kWh ({avg_discount/total_avg*100:>5.1f}%) @ 4.347¢/kWh")
        print(f"  Avg demand charges: ${tou_costs['demand_charge'].mean():.2f}/month")

        # TOU-EV breakdown
        avg_ev_discount = tou_ev_costs['discount_kwh'].mean()
        avg_ev_standard = tou_ev_costs['standard_kwh'].mean()
        total_ev_avg = avg_ev_discount + avg_ev_standard

        print(f"\nR-TOU-EV (Simplified TOU for EV owners, no demand charges):")
        print(f"  Discount:     {avg_ev_discount:>8.1f} kWh ({avg_ev_discount/total_ev_avg*100:>5.1f}%) @ 6.548¢/kWh (11 PM - 5 AM)")
        print(f"  Standard:     {avg_ev_standard:>8.1f} kWh ({avg_ev_standard/total_ev_avg*100:>5.1f}%) @ 13.096¢/kWh (all other hours)")
        print(f"  No demand charges!")

        print("\n" + "-" * 80)
        print("RECOMMENDATIONS:")
        print("-" * 80)

        if best_rate[0] == 'TOU-EV':
            print(f"  ★★★ STRONGLY RECOMMEND: Switch to TOU-EV Rate (R-TOU-EV)")
            print(f"      - Saves ${tou_ev_savings:.2f}/year vs Standard ({tou_ev_pct:.1f}%)")
            if tou_ev_vs_tou_savings > 0:
                print(f"      - Saves ${tou_ev_vs_tou_savings:.2f}/year vs regular TOU")
            print(f"      - No demand charges (saves ~${tou_costs['demand_charge'].mean():.2f}/month)")
            print(f"      - Simple rate structure with long discount window (11 PM - 5 AM)")
            print(f"      - You use {avg_ev_discount/total_ev_avg*100:.1f}% during discount hours")
            print(f"\n  ACTION: Contact Duke Energy to switch to R-TOU-EV")
            print(f"          - Must provide proof of EV ownership/lease")
            print(f"          - Pilot limited to 20,000 customers - enroll soon!")
        elif best_rate[0] == 'TOU':
            print(f"  ✓ RECOMMEND: Time-of-Use Rate (R-TOUD)")
            print(f"      - Saves ${tou_savings:.2f}/year vs Standard ({tou_pct:.1f}%)")
            if tou_ev_savings > tou_savings:
                print(f"      - TOU-EV would save even more (${tou_ev_savings:.2f}/year)")
                print(f"      - Consider TOU-EV if you own/lease an electric vehicle")
        else:
            print(f"  • Standard rate is currently cheapest")
            print(f"  • To benefit from TOU-EV:")
            print(f"    - Shift more usage to 11 PM - 5 AM (only 6.548¢/kWh)")
            print(f"    - Currently using {avg_ev_discount/total_ev_avg*100:.1f}% during this window")

        print("\n" + "=" * 80)


def main():
    """Example usage - Compare all three rate schedules"""

    # Parse energy data
    print("Loading energy usage data...")
    # Duke Energy operates in Eastern Time
    parser = EnergyUsageParser("Energy Usage.xml", timezone='America/New_York')
    data = parser.parse()
    energy_df = parser.to_dataframe()

    # Initialize rate calculator
    print("Initializing Duke Energy rate calculator...")
    calculator = DukeEnergyRateCalculator()

    # Compare all three rates
    print("Calculating costs under all three rate schedules...")
    standard_costs, tou_costs, tou_ev_costs, comparison, comparison_all = calculator.compare_rates(energy_df)

    # Print comprehensive summary
    calculator.print_all_rates_summary(standard_costs, tou_costs, tou_ev_costs, comparison_all)

    # Create visualizations
    print("\nGenerating comparison plots...")
    calculator.plot_all_rates_comparison(comparison_all, save_path='rate_comparison_all.png')

    # Save detailed results to CSV
    print("\nSaving detailed results...")
    standard_costs.to_csv('standard_rate_costs.csv', index=False)
    tou_costs.to_csv('tou_rate_costs.csv', index=False)
    tou_ev_costs.to_csv('tou_ev_rate_costs.csv', index=False)
    comparison_all.to_csv('rate_comparison_all_summary.csv', index=False)

    print("\nDone! Files saved:")
    print("  - rate_comparison_all.png")
    print("  - standard_rate_costs.csv")
    print("  - tou_rate_costs.csv")
    print("  - tou_ev_rate_costs.csv")
    print("  - rate_comparison_all_summary.csv")


if __name__ == "__main__":
    main()
