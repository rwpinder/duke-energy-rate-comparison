"""
Energy Usage XML Parser
Parses Green Button ESPI (Energy Services Provider Interface) XML files
"""

import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Dict, Optional
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from scipy import stats
import requests
from urllib.parse import urlencode


class EnergyUsageParser:
    """Parser for Green Button Energy Usage XML files"""

    # Define XML namespaces
    NAMESPACES = {
        'ns3': 'http://www.w3.org/2005/Atom',
        'espi': 'http://naesb.org/espi'
    }

    def __init__(self, xml_file_path: str):
        """
        Initialize the parser with an XML file path

        Args:
            xml_file_path: Path to the Energy Usage XML file
        """
        self.xml_file_path = xml_file_path
        self.tree = None
        self.root = None
        self.meter_info = {}
        self.interval_readings = []

    def parse(self) -> Dict:
        """
        Parse the XML file and extract all data

        Returns:
            Dictionary containing meter information and interval readings
        """
        # Parse the XML file
        self.tree = ET.parse(self.xml_file_path)
        self.root = self.tree.getroot()

        # Extract meter information
        self._extract_meter_info()

        # Extract interval readings
        self._extract_interval_readings()

        return {
            'meter_info': self.meter_info,
            'readings': self.interval_readings
        }

    def _extract_meter_info(self):
        """Extract meter and service point information"""
        interval = self.root.find('.//espi:interval', self.NAMESPACES)

        if interval is not None:
            # Service Point ID
            service_point = interval.find('espi:servicePointId', self.NAMESPACES)
            if service_point is not None:
                self.meter_info['service_point_id'] = service_point.text

            # Meter information
            meter = interval.find('espi:Meter', self.NAMESPACES)
            if meter is not None:
                serial = meter.find('espi:meterSerialNumber', self.NAMESPACES)
                install_date = meter.find('espi:meterInstallDate', self.NAMESPACES)

                if serial is not None:
                    self.meter_info['meter_serial_number'] = serial.text.strip()
                if install_date is not None:
                    self.meter_info['meter_install_date'] = install_date.text

            # Service information
            service_type = interval.find('espi:serviceType', self.NAMESPACES)
            unit_of_measure = interval.find('espi:unitOfMeasure', self.NAMESPACES)
            seconds_per_interval = interval.find('espi:secondsPerInterval', self.NAMESPACES)

            if service_type is not None:
                self.meter_info['service_type'] = service_type.text
            if unit_of_measure is not None:
                self.meter_info['unit_of_measure'] = unit_of_measure.text
            if seconds_per_interval is not None:
                self.meter_info['seconds_per_interval'] = int(seconds_per_interval.text)
                self.meter_info['minutes_per_interval'] = int(seconds_per_interval.text) // 60

    def _extract_interval_readings(self):
        """Extract all interval readings with timestamps and values"""
        readings = self.root.findall('.//espi:IntervalReading', self.NAMESPACES)

        for reading in readings:
            time_period = reading.find('espi:timePeriod', self.NAMESPACES)
            quality = reading.find('espi:readingQuality', self.NAMESPACES)
            value = reading.find('espi:value', self.NAMESPACES)

            if time_period is not None and value is not None:
                start_elem = time_period.find('espi:start', self.NAMESPACES)

                if start_elem is not None:
                    timestamp = int(start_elem.text)
                    reading_data = {
                        'timestamp': timestamp,
                        'datetime': datetime.fromtimestamp(timestamp),
                        'value': float(value.text),
                        'quality': quality.text if quality is not None else None
                    }
                    self.interval_readings.append(reading_data)

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert interval readings to a pandas DataFrame

        Returns:
            DataFrame with datetime index and energy usage values
        """
        if not self.interval_readings:
            self.parse()

        df = pd.DataFrame(self.interval_readings)
        df = df.sort_values('datetime')
        df = df.set_index('datetime')
        return df

    def get_summary_statistics(self) -> Dict:
        """
        Calculate summary statistics for the energy usage data

        Returns:
            Dictionary containing summary statistics
        """
        if not self.interval_readings:
            self.parse()

        values = [r['value'] for r in self.interval_readings]

        return {
            'total_readings': len(values),
            'total_usage': sum(values),
            'average_usage': sum(values) / len(values) if values else 0,
            'min_usage': min(values) if values else 0,
            'max_usage': max(values) if values else 0,
            'first_reading': self.interval_readings[0]['datetime'] if self.interval_readings else None,
            'last_reading': self.interval_readings[-1]['datetime'] if self.interval_readings else None,
            'unit': self.meter_info.get('unit_of_measure', 'unknown')
        }

    def print_summary(self):
        """Print a formatted summary of the parsed data"""
        if not self.meter_info or not self.interval_readings:
            self.parse()

        print("=" * 60)
        print("METER INFORMATION")
        print("=" * 60)
        for key, value in self.meter_info.items():
            print(f"{key.replace('_', ' ').title()}: {value}")

        print("\n" + "=" * 60)
        print("USAGE STATISTICS")
        print("=" * 60)
        stats = self.get_summary_statistics()
        for key, value in stats.items():
            print(f"{key.replace('_', ' ').title()}: {value}")

        print("\n" + "=" * 60)
        print("SAMPLE READINGS (First 5)")
        print("=" * 60)
        for reading in self.interval_readings[:5]:
            print(f"{reading['datetime']}: {reading['value']} {self.meter_info.get('unit_of_measure', '')}")

    def get_daily_averages(self) -> pd.DataFrame:
        """
        Calculate daily average energy usage

        Returns:
            DataFrame with daily average values indexed by date
        """
        df = self.to_dataframe()
        daily_avg = df.groupby(df.index.date)['value'].mean()
        daily_avg.index = pd.to_datetime(daily_avg.index)
        return daily_avg

    def get_daily_maximums(self) -> pd.DataFrame:
        """
        Calculate daily maximum energy usage

        Returns:
            DataFrame with daily maximum values indexed by date
        """
        df = self.to_dataframe()
        daily_max = df.groupby(df.index.date)['value'].max()
        daily_max.index = pd.to_datetime(daily_max.index)
        return daily_max

    def get_hourly_averages(self) -> pd.Series:
        """
        Calculate average energy usage for each hour of the day (diurnal pattern)

        Returns:
            Series with 24 values (0-23) representing average usage for each hour
        """
        df = self.to_dataframe()
        hourly_avg = df.groupby(df.index.hour)['value'].mean()
        return hourly_avg

    def get_baseload(self) -> Dict:
        """
        Calculate baseload - the minimum continuous power draw

        Returns:
            Dictionary with baseload statistics
        """
        hourly_avg = self.get_hourly_averages()

        # Baseload is typically the minimum hourly average (usually nighttime)
        baseload = hourly_avg.min()
        baseload_hour = hourly_avg.idxmin()

        # Calculate what percentage of daily usage is baseload
        daily_avg = self.get_daily_averages().mean()
        baseload_percentage = (baseload / daily_avg * 100) if daily_avg > 0 else 0

        return {
            'baseload_kwh': baseload,
            'baseload_hour': baseload_hour,
            'baseload_percentage': baseload_percentage,
            'estimated_daily_baseload': baseload * 24,
            'estimated_monthly_baseload': baseload * 24 * 30
        }

    def get_weekday_weekend_comparison(self) -> Dict:
        """
        Compare energy usage between weekdays and weekends

        Returns:
            Dictionary with weekday vs weekend statistics
        """
        df = self.to_dataframe()

        # Add day of week (0=Monday, 6=Sunday)
        df_copy = df.copy()
        df_copy['day_of_week'] = df_copy.index.dayofweek
        df_copy['is_weekend'] = df_copy['day_of_week'].isin([5, 6])

        weekday_avg = df_copy[~df_copy['is_weekend']]['value'].mean()
        weekend_avg = df_copy[df_copy['is_weekend']]['value'].mean()

        # Get hourly patterns
        weekday_hourly = df_copy[~df_copy['is_weekend']].groupby(df_copy[~df_copy['is_weekend']].index.hour)['value'].mean()
        weekend_hourly = df_copy[df_copy['is_weekend']].groupby(df_copy[df_copy['is_weekend']].index.hour)['value'].mean()

        return {
            'weekday_average': weekday_avg,
            'weekend_average': weekend_avg,
            'difference': weekend_avg - weekday_avg,
            'difference_percentage': ((weekend_avg - weekday_avg) / weekday_avg * 100) if weekday_avg > 0 else 0,
            'weekday_hourly': weekday_hourly,
            'weekend_hourly': weekend_hourly
        }

    def get_energy_insights(self) -> Dict:
        """
        Generate comprehensive energy usage insights for conservation opportunities

        Returns:
            Dictionary with various insights and recommendations
        """
        df = self.to_dataframe()
        hourly_avg = self.get_hourly_averages()
        baseload_info = self.get_baseload()

        # Find peak usage times
        peak_hour = hourly_avg.idxmax()
        peak_value = hourly_avg.max()

        # Calculate variability
        daily_totals = df.groupby(df.index.date)['value'].sum()
        daily_std = daily_totals.std()
        daily_mean = daily_totals.mean()

        # Find top 10 highest usage intervals
        top_intervals = df.nlargest(10, 'value')

        insights = {
            'baseload': baseload_info,
            'peak_hour': peak_hour,
            'peak_value': peak_value,
            'peak_to_baseload_ratio': peak_value / baseload_info['baseload_kwh'] if baseload_info['baseload_kwh'] > 0 else 0,
            'daily_variability_std': daily_std,
            'daily_variability_cv': (daily_std / daily_mean * 100) if daily_mean > 0 else 0,
            'top_usage_times': top_intervals
        }

        return insights

    def print_energy_insights(self):
        """Print energy insights with conservation recommendations"""
        insights = self.get_energy_insights()
        unit = self.meter_info.get('unit_of_measure', 'kWH')

        print("\n" + "=" * 70)
        print("ENERGY CONSERVATION INSIGHTS")
        print("=" * 70)

        print("\n1. BASELOAD ANALYSIS")
        print("-" * 70)
        baseload = insights['baseload']
        print(f"   Minimum Usage (Baseload): {baseload['baseload_kwh']:.2f} {unit} at hour {baseload['baseload_hour']}:00")
        print(f"   Baseload Percentage: {baseload['baseload_percentage']:.1f}% of average usage")
        print(f"   Est. Monthly Baseload Cost: {baseload['estimated_monthly_baseload']:.1f} {unit}")
        print("\n   💡 RECOMMENDATION:")
        if baseload['baseload_percentage'] > 40:
            print("      ⚠️  HIGH baseload! Look for:")
            print("      • Devices in standby mode (TVs, computers, chargers)")
            print("      • Old/inefficient refrigerators or freezers")
            print("      • Always-on devices that could be on timers")
        else:
            print("      ✓ Baseload is reasonable")

        print("\n2. PEAK USAGE ANALYSIS")
        print("-" * 70)
        print(f"   Peak Hour: {insights['peak_hour']}:00")
        print(f"   Peak Usage: {insights['peak_value']:.2f} {unit}")
        print(f"   Peak-to-Baseload Ratio: {insights['peak_to_baseload_ratio']:.1f}x")
        print("\n   💡 RECOMMENDATION:")
        if 6 <= insights['peak_hour'] <= 9:
            print("      Morning peak detected - Consider:")
            print("      • Water heater timer (heat water overnight)")
            print("      • Delay dishwasher/laundry to off-peak")
        elif 17 <= insights['peak_hour'] <= 21:
            print("      Evening peak detected - Consider:")
            print("      • HVAC thermostat adjustment during peak hours")
            print("      • Use slow cooker instead of oven")
            print("      • Run major appliances after 9 PM")

        print("\n3. USAGE VARIABILITY")
        print("-" * 70)
        print(f"   Daily Variation (CV): {insights['daily_variability_cv']:.1f}%")
        print("\n   💡 RECOMMENDATION:")
        if insights['daily_variability_cv'] > 30:
            print("      High variability suggests opportunity for consistency")
            print("      • Review high-usage days for discretionary loads")

        print("\n4. TOP 10 HIGHEST USAGE INTERVALS")
        print("-" * 70)
        for i, (timestamp, row) in enumerate(insights['top_usage_times'].iterrows(), 1):
            print(f"   {i}. {timestamp.strftime('%Y-%m-%d %H:%M')} - {row['value']:.2f} {unit}")
        print("\n   💡 RECOMMENDATION:")
        print("      Review what was happening during these times")
        print("      These are your biggest opportunities for reduction")

        # Weekday vs Weekend
        try:
            ww_compare = self.get_weekday_weekend_comparison()
            print("\n5. WEEKDAY VS WEEKEND COMPARISON")
            print("-" * 70)
            print(f"   Weekday Average: {ww_compare['weekday_average']:.2f} {unit}")
            print(f"   Weekend Average: {ww_compare['weekend_average']:.2f} {unit}")
            print(f"   Difference: {ww_compare['difference']:.2f} {unit} ({ww_compare['difference_percentage']:.1f}%)")
            print("\n   💡 RECOMMENDATION:")
            if abs(ww_compare['difference_percentage']) > 15:
                if ww_compare['difference'] > 0:
                    print("      Higher weekend usage - likely more time at home")
                else:
                    print("      Higher weekday usage - check if devices left on while away")
        except Exception as e:
            print(f"\n5. WEEKDAY VS WEEKEND: Unable to calculate ({str(e)})")

        print("\n" + "=" * 70)

    def plot_daily_averages(self, save_path: Optional[str] = None, show: bool = True):
        """
        Create a time series plot of daily average energy usage

        Args:
            save_path: Optional path to save the plot (e.g., 'daily_usage.png')
            show: Whether to display the plot (default: True)
        """
        daily_avg = self.get_daily_averages()
        unit = self.meter_info.get('unit_of_measure', 'Energy')

        # Create the plot
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(daily_avg.index, daily_avg.values, marker='o', linestyle='-',
                linewidth=2, markersize=4, color='#2E86AB')

        # Format the plot
        ax.set_xlabel('Date', fontsize=12, fontweight='bold')
        ax.set_ylabel(f'Average Daily Usage ({unit})', fontsize=12, fontweight='bold')
        ax.set_title('Daily Average Energy Usage', fontsize=14, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--')

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right')

        # Add some padding
        plt.tight_layout()

        # Save if path provided
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        # Show the plot
        if show:
            plt.show()

        return fig, ax

    def plot_daily_maximums(self, save_path: Optional[str] = None, show: bool = True):
        """
        Create a time series plot of daily maximum energy usage

        Args:
            save_path: Optional path to save the plot (e.g., 'daily_max_usage.png')
            show: Whether to display the plot (default: True)
        """
        daily_max = self.get_daily_maximums()
        unit = self.meter_info.get('unit_of_measure', 'Energy')

        # Create the plot
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(daily_max.index, daily_max.values, marker='o', linestyle='-',
                linewidth=2, markersize=4, color='#A23B72')

        # Format the plot
        ax.set_xlabel('Date', fontsize=12, fontweight='bold')
        ax.set_ylabel(f'Maximum Daily Usage ({unit})', fontsize=12, fontweight='bold')
        ax.set_title('Daily Maximum Energy Usage', fontsize=14, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--')

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right')

        # Add some padding
        plt.tight_layout()

        # Save if path provided
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        # Show the plot
        if show:
            plt.show()

        return fig, ax

    def plot_daily_comparison(self, save_path: Optional[str] = None, show: bool = True):
        """
        Create a time series plot comparing daily average and maximum energy usage

        Args:
            save_path: Optional path to save the plot (e.g., 'daily_comparison.png')
            show: Whether to display the plot (default: True)
        """
        daily_avg = self.get_daily_averages()
        daily_max = self.get_daily_maximums()
        unit = self.meter_info.get('unit_of_measure', 'Energy')

        # Create the plot
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(daily_avg.index, daily_avg.values, marker='o', linestyle='-',
                linewidth=2, markersize=4, color='#2E86AB', label='Average')
        ax.plot(daily_max.index, daily_max.values, marker='s', linestyle='-',
                linewidth=2, markersize=4, color='#A23B72', label='Maximum')

        # Format the plot
        ax.set_xlabel('Date', fontsize=12, fontweight='bold')
        ax.set_ylabel(f'Daily Usage ({unit})', fontsize=12, fontweight='bold')
        ax.set_title('Daily Average vs Maximum Energy Usage', fontsize=14, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.legend(loc='best', fontsize=11)

        # Format x-axis dates
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right')

        # Add some padding
        plt.tight_layout()

        # Save if path provided
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        # Show the plot
        if show:
            plt.show()

        return fig, ax

    def plot_diurnal_pattern(self, save_path: Optional[str] = None, show: bool = True):
        """
        Create a diurnal plot showing average energy usage by hour of day

        Args:
            save_path: Optional path to save the plot (e.g., 'diurnal_pattern.png')
            show: Whether to display the plot (default: True)
        """
        hourly_avg = self.get_hourly_averages()
        unit = self.meter_info.get('unit_of_measure', 'Energy')

        # Create the plot
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(hourly_avg.index, hourly_avg.values, marker='o', linestyle='-',
                linewidth=2.5, markersize=6, color='#18A558')
        ax.fill_between(hourly_avg.index, hourly_avg.values, alpha=0.3, color='#18A558')

        # Format the plot
        ax.set_xlabel('Hour of Day', fontsize=12, fontweight='bold')
        ax.set_ylabel(f'Average Usage ({unit})', fontsize=12, fontweight='bold')
        ax.set_title('Diurnal Energy Usage Pattern (Average by Hour)', fontsize=14, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--')

        # Set x-axis to show all 24 hours
        ax.set_xlim(-0.5, 23.5)
        ax.set_xticks(range(0, 24, 2))
        ax.set_xticklabels([f'{h:02d}:00' for h in range(0, 24, 2)])

        # Add some padding
        plt.tight_layout()

        # Save if path provided
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        # Show the plot
        if show:
            plt.show()

        return fig, ax

    def fetch_weather_data(self, latitude: float = 35.9101, longitude: float = -79.0753) -> pd.DataFrame:
        """
        Fetch historical weather data from Open-Meteo API
        Default coordinates are for Carrboro, NC

        Args:
            latitude: Location latitude (default: Carrboro, NC)
            longitude: Location longitude (default: Carrboro, NC)

        Returns:
            DataFrame with hourly temperature and relative humidity
        """
        if not self.interval_readings:
            self.parse()

        # Get date range from energy data
        start_date = self.interval_readings[0]['datetime'].date()
        end_date = self.interval_readings[-1]['datetime'].date()

        print(f"Fetching weather data for {start_date} to {end_date}...")

        # Open-Meteo API (free, no key required)
        base_url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            'latitude': latitude,
            'longitude': longitude,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'hourly': 'temperature_2m,relative_humidity_2m',
            'temperature_unit': 'fahrenheit',
            'timezone': 'America/New_York'
        }

        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        # Parse the response
        weather_df = pd.DataFrame({
            'datetime': pd.to_datetime(data['hourly']['time']),
            'temperature_f': data['hourly']['temperature_2m'],
            'relative_humidity': data['hourly']['relative_humidity_2m']
        })

        weather_df = weather_df.set_index('datetime')
        print(f"Retrieved {len(weather_df)} hourly weather observations")

        return weather_df

    def merge_with_weather(self, weather_df: Optional[pd.DataFrame] = None,
                          latitude: float = 35.9101, longitude: float = -79.0753) -> pd.DataFrame:
        """
        Merge energy usage data with weather data

        Args:
            weather_df: Optional pre-loaded weather DataFrame
            latitude: Location latitude (used if weather_df not provided)
            longitude: Location longitude (used if weather_df not provided)

        Returns:
            DataFrame with energy usage and weather data merged
        """
        if weather_df is None:
            weather_df = self.fetch_weather_data(latitude, longitude)

        energy_df = self.to_dataframe()

        # Merge on datetime index
        merged_df = energy_df.join(weather_df, how='left')

        # Forward fill any missing weather values (shouldn't be many)
        merged_df['temperature_f'] = merged_df['temperature_f'].fillna(method='ffill')
        merged_df['relative_humidity'] = merged_df['relative_humidity'].fillna(method='ffill')

        return merged_df

    def calculate_weather_correlation(self, weather_df: Optional[pd.DataFrame] = None) -> Dict:
        """
        Calculate correlation between energy usage and weather

        Args:
            weather_df: Optional pre-loaded weather DataFrame

        Returns:
            Dictionary with correlation statistics
        """
        merged_df = self.merge_with_weather(weather_df)

        # Calculate correlations
        temp_corr = merged_df['value'].corr(merged_df['temperature_f'])
        rh_corr = merged_df['value'].corr(merged_df['relative_humidity'])

        # Linear regression for temperature
        temp_slope, temp_intercept, temp_r_value, temp_p_value, temp_std_err = \
            stats.linregress(merged_df['temperature_f'].dropna(),
                           merged_df.loc[merged_df['temperature_f'].notna(), 'value'])

        # Linear regression for humidity
        rh_slope, rh_intercept, rh_r_value, rh_p_value, rh_std_err = \
            stats.linregress(merged_df['relative_humidity'].dropna(),
                           merged_df.loc[merged_df['relative_humidity'].notna(), 'value'])

        return {
            'temperature_correlation': temp_corr,
            'temperature_r_squared': temp_r_value ** 2,
            'temperature_p_value': temp_p_value,
            'temperature_slope': temp_slope,
            'humidity_correlation': rh_corr,
            'humidity_r_squared': rh_r_value ** 2,
            'humidity_p_value': rh_p_value,
            'humidity_slope': rh_slope,
            'merged_data': merged_df
        }

    def plot_weather_correlation(self, weather_df: Optional[pd.DataFrame] = None,
                                 save_path: Optional[str] = None, show: bool = True):
        """
        Create scatter plots showing correlation between energy usage and weather

        Args:
            weather_df: Optional pre-loaded weather DataFrame
            save_path: Optional path to save the plot
            show: Whether to display the plot
        """
        correlation_data = self.calculate_weather_correlation(weather_df)
        merged_df = correlation_data['merged_data']
        unit = self.meter_info.get('unit_of_measure', 'kWH')

        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        # Temperature scatter plot
        ax1.scatter(merged_df['temperature_f'], merged_df['value'],
                   alpha=0.5, s=10, color='#E63946')

        # Add trend line
        z = np.polyfit(merged_df['temperature_f'].dropna(),
                      merged_df.loc[merged_df['temperature_f'].notna(), 'value'], 1)
        p = np.poly1d(z)
        temp_sorted = sorted(merged_df['temperature_f'].dropna())
        ax1.plot(temp_sorted, p(temp_sorted), "r--", linewidth=2, alpha=0.8)

        ax1.set_xlabel('Temperature (°F)', fontsize=12, fontweight='bold')
        ax1.set_ylabel(f'Energy Usage ({unit})', fontsize=12, fontweight='bold')
        ax1.set_title(f'Energy vs Temperature\nr = {correlation_data["temperature_correlation"]:.3f}, '
                     f'R² = {correlation_data["temperature_r_squared"]:.3f}',
                     fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Humidity scatter plot
        ax2.scatter(merged_df['relative_humidity'], merged_df['value'],
                   alpha=0.5, s=10, color='#457B9D')

        # Add trend line
        z = np.polyfit(merged_df['relative_humidity'].dropna(),
                      merged_df.loc[merged_df['relative_humidity'].notna(), 'value'], 1)
        p = np.poly1d(z)
        rh_sorted = sorted(merged_df['relative_humidity'].dropna())
        ax2.plot(rh_sorted, p(rh_sorted), "b--", linewidth=2, alpha=0.8)

        ax2.set_xlabel('Relative Humidity (%)', fontsize=12, fontweight='bold')
        ax2.set_ylabel(f'Energy Usage ({unit})', fontsize=12, fontweight='bold')
        ax2.set_title(f'Energy vs Humidity\nr = {correlation_data["humidity_correlation"]:.3f}, '
                     f'R² = {correlation_data["humidity_r_squared"]:.3f}',
                     fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        if show:
            plt.show()

        return fig, (ax1, ax2)

    def plot_energy_weather_timeseries(self, weather_df: Optional[pd.DataFrame] = None,
                                      save_path: Optional[str] = None, show: bool = True):
        """
        Create time series plot with energy usage and temperature on same chart

        Args:
            weather_df: Optional pre-loaded weather DataFrame
            save_path: Optional path to save the plot
            show: Whether to display the plot
        """
        merged_df = self.merge_with_weather(weather_df)

        # Aggregate to daily for cleaner visualization
        daily_energy = merged_df.groupby(merged_df.index.date)['value'].mean()
        daily_temp = merged_df.groupby(merged_df.index.date)['temperature_f'].mean()

        daily_energy.index = pd.to_datetime(daily_energy.index)
        daily_temp.index = pd.to_datetime(daily_temp.index)

        unit = self.meter_info.get('unit_of_measure', 'kWH')

        # Create figure with dual y-axes
        fig, ax1 = plt.subplots(figsize=(14, 6))

        color1 = '#2E86AB'
        ax1.set_xlabel('Date', fontsize=12, fontweight='bold')
        ax1.set_ylabel(f'Energy Usage ({unit})', color=color1, fontsize=12, fontweight='bold')
        ax1.plot(daily_energy.index, daily_energy.values, color=color1, linewidth=2, label='Energy Usage')
        ax1.tick_params(axis='y', labelcolor=color1)
        ax1.grid(True, alpha=0.3)

        # Create second y-axis for temperature
        ax2 = ax1.twinx()
        color2 = '#E63946'
        ax2.set_ylabel('Temperature (°F)', color=color2, fontsize=12, fontweight='bold')
        ax2.plot(daily_temp.index, daily_temp.values, color=color2, linewidth=2,
                linestyle='--', label='Temperature')
        ax2.tick_params(axis='y', labelcolor=color2)

        # Format x-axis
        ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
        plt.xticks(rotation=45, ha='right')

        plt.title('Daily Energy Usage vs Temperature', fontsize=14, fontweight='bold', pad=20)

        # Add legends
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc='upper left')

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        if show:
            plt.show()

        return fig, (ax1, ax2)

    def calculate_degree_days(self, weather_df: Optional[pd.DataFrame] = None,
                              base_temp: float = 65.0) -> pd.DataFrame:
        """
        Calculate cooling and heating degree days from weather data

        Args:
            weather_df: Optional pre-loaded weather DataFrame
            base_temp: Base temperature for degree day calculation (default: 65°F)

        Returns:
            DataFrame with daily degree days
        """
        merged_df = self.merge_with_weather(weather_df)

        # Calculate daily average temperature
        daily_temp = merged_df.groupby(merged_df.index.date)['temperature_f'].mean()
        daily_temp.index = pd.to_datetime(daily_temp.index)

        # Calculate degree days
        degree_days_df = pd.DataFrame({
            'avg_temp': daily_temp,
            'cooling_degree_days': np.maximum(0, daily_temp - base_temp),
            'heating_degree_days': np.maximum(0, base_temp - daily_temp)
        })

        # Add season information
        degree_days_df['month'] = degree_days_df.index.month
        degree_days_df['season'] = degree_days_df['month'].apply(self._get_season)

        return degree_days_df

    @staticmethod
    def _get_season(month: int) -> str:
        """Helper function to determine season from month"""
        if month in [12, 1, 2]:
            return 'winter'
        elif month in [3, 4, 5]:
            return 'spring'
        elif month in [6, 7, 8]:
            return 'summer'
        else:  # 9, 10, 11
            return 'fall'

    def analyze_degree_day_correlation(self, weather_df: Optional[pd.DataFrame] = None,
                                      seasons: Optional[list] = None,
                                      hour_of_day: Optional[int] = None,
                                      base_temp: float = 65.0) -> Dict:
        """
        Analyze correlation between energy usage and degree days

        Args:
            weather_df: Optional pre-loaded weather DataFrame
            seasons: List of seasons to include ['winter', 'spring', 'summer', 'fall']
                    If None, includes all seasons
            hour_of_day: Specific hour (0-23) to analyze. If None, uses daily average
            base_temp: Base temperature for degree day calculation (default: 65°F)

        Returns:
            Dictionary with degree day correlation statistics
        """
        merged_df = self.merge_with_weather(weather_df)

        # Filter by hour if specified
        if hour_of_day is not None:
            if not 0 <= hour_of_day <= 23:
                raise ValueError("hour_of_day must be between 0 and 23")
            merged_df = merged_df[merged_df.index.hour == hour_of_day]

        # Calculate daily aggregates
        daily_energy = merged_df.groupby(merged_df.index.date)['value'].mean()
        daily_temp = merged_df.groupby(merged_df.index.date)['temperature_f'].mean()

        daily_energy.index = pd.to_datetime(daily_energy.index)
        daily_temp.index = pd.to_datetime(daily_temp.index)

        # Calculate degree days
        cdd = np.maximum(0, daily_temp - base_temp)
        hdd = np.maximum(0, base_temp - daily_temp)

        # Create combined dataframe
        analysis_df = pd.DataFrame({
            'energy': daily_energy,
            'temperature': daily_temp,
            'cdd': cdd,
            'hdd': hdd,
            'month': daily_energy.index.month
        })

        # Add season
        analysis_df['season'] = analysis_df['month'].apply(self._get_season)

        # Filter by seasons if specified
        if seasons is not None:
            analysis_df = analysis_df[analysis_df['season'].isin(seasons)]

        # Calculate correlations
        cdd_corr = analysis_df['energy'].corr(analysis_df['cdd'])
        hdd_corr = analysis_df['energy'].corr(analysis_df['hdd'])

        # Linear regression for CDD (only days with CDD > 0)
        cdd_data = analysis_df[analysis_df['cdd'] > 0]
        if len(cdd_data) > 1:
            cdd_slope, cdd_intercept, cdd_r_value, cdd_p_value, cdd_std_err = \
                stats.linregress(cdd_data['cdd'], cdd_data['energy'])
        else:
            cdd_slope = cdd_intercept = cdd_r_value = cdd_p_value = cdd_std_err = np.nan

        # Linear regression for HDD (only days with HDD > 0)
        hdd_data = analysis_df[analysis_df['hdd'] > 0]
        if len(hdd_data) > 1:
            hdd_slope, hdd_intercept, hdd_r_value, hdd_p_value, hdd_std_err = \
                stats.linregress(hdd_data['hdd'], hdd_data['energy'])
        else:
            hdd_slope = hdd_intercept = hdd_r_value = hdd_p_value = hdd_std_err = np.nan

        return {
            'cdd_correlation': cdd_corr,
            'cdd_r_squared': cdd_r_value ** 2 if not np.isnan(cdd_r_value) else np.nan,
            'cdd_p_value': cdd_p_value,
            'cdd_slope': cdd_slope,
            'cdd_intercept': cdd_intercept,
            'hdd_correlation': hdd_corr,
            'hdd_r_squared': hdd_r_value ** 2 if not np.isnan(hdd_r_value) else np.nan,
            'hdd_p_value': hdd_p_value,
            'hdd_slope': hdd_slope,
            'hdd_intercept': hdd_intercept,
            'analysis_data': analysis_df,
            'base_temp': base_temp,
            'seasons': seasons if seasons else ['winter', 'spring', 'summer', 'fall'],
            'hour_of_day': hour_of_day
        }

    def plot_degree_day_correlation(self, weather_df: Optional[pd.DataFrame] = None,
                                   seasons: Optional[list] = None,
                                   hour_of_day: Optional[int] = None,
                                   base_temp: float = 65.0,
                                   save_path: Optional[str] = None,
                                   show: bool = True):
        """
        Create scatter plots of energy usage vs degree days

        Args:
            weather_df: Optional pre-loaded weather DataFrame
            seasons: List of seasons to include
            hour_of_day: Specific hour to analyze (0-23)
            base_temp: Base temperature for degree days
            save_path: Optional path to save the plot
            show: Whether to display the plot
        """
        dd_data = self.analyze_degree_day_correlation(weather_df, seasons, hour_of_day, base_temp)
        analysis_df = dd_data['analysis_data']
        unit = self.meter_info.get('unit_of_measure', 'kWH')

        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        # Cooling Degree Days plot
        cdd_data = analysis_df[analysis_df['cdd'] > 0]
        if len(cdd_data) > 0:
            ax1.scatter(cdd_data['cdd'], cdd_data['energy'],
                       alpha=0.6, s=30, color='#E63946', edgecolors='darkred', linewidth=0.5)

            # Add trend line
            if not np.isnan(dd_data['cdd_slope']):
                x_range = np.array([cdd_data['cdd'].min(), cdd_data['cdd'].max()])
                y_pred = dd_data['cdd_slope'] * x_range + dd_data['cdd_intercept']
                ax1.plot(x_range, y_pred, "r--", linewidth=2.5, alpha=0.8, label='Trend')

        ax1.set_xlabel(f'Cooling Degree Days (base {base_temp}°F)', fontsize=12, fontweight='bold')
        ax1.set_ylabel(f'Energy Usage ({unit})', fontsize=12, fontweight='bold')
        title1 = f'Energy vs Cooling Degree Days\nr = {dd_data["cdd_correlation"]:.3f}'
        if not np.isnan(dd_data['cdd_r_squared']):
            title1 += f', R² = {dd_data["cdd_r_squared"]:.3f}'
        ax1.set_title(title1, fontsize=12, fontweight='bold')
        ax1.grid(True, alpha=0.3)

        # Heating Degree Days plot
        hdd_data = analysis_df[analysis_df['hdd'] > 0]
        if len(hdd_data) > 0:
            ax2.scatter(hdd_data['hdd'], hdd_data['energy'],
                       alpha=0.6, s=30, color='#457B9D', edgecolors='darkblue', linewidth=0.5)

            # Add trend line
            if not np.isnan(dd_data['hdd_slope']):
                x_range = np.array([hdd_data['hdd'].min(), hdd_data['hdd'].max()])
                y_pred = dd_data['hdd_slope'] * x_range + dd_data['hdd_intercept']
                ax2.plot(x_range, y_pred, "b--", linewidth=2.5, alpha=0.8, label='Trend')

        ax2.set_xlabel(f'Heating Degree Days (base {base_temp}°F)', fontsize=12, fontweight='bold')
        ax2.set_ylabel(f'Energy Usage ({unit})', fontsize=12, fontweight='bold')
        title2 = f'Energy vs Heating Degree Days\nr = {dd_data["hdd_correlation"]:.3f}'
        if not np.isnan(dd_data['hdd_r_squared']):
            title2 += f', R² = {dd_data["hdd_r_squared"]:.3f}'
        ax2.set_title(title2, fontsize=12, fontweight='bold')
        ax2.grid(True, alpha=0.3)

        # Add subtitle with filter info
        filter_text = f"Seasons: {', '.join(dd_data['seasons'])}"
        if hour_of_day is not None:
            filter_text += f" | Hour: {hour_of_day}:00"
        fig.suptitle(filter_text, fontsize=10, y=0.02)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"Plot saved to: {save_path}")

        if show:
            plt.show()

        return fig, (ax1, ax2)

    def print_degree_day_insights(self, weather_df: Optional[pd.DataFrame] = None,
                                 seasons: Optional[list] = None,
                                 hour_of_day: Optional[int] = None,
                                 base_temp: float = 65.0):
        """Print degree day correlation insights"""
        dd_data = self.analyze_degree_day_correlation(weather_df, seasons, hour_of_day, base_temp)
        unit = self.meter_info.get('unit_of_measure', 'kWH')

        print("\n" + "=" * 70)
        print("DEGREE DAY CORRELATION ANALYSIS")
        print("=" * 70)

        print(f"\nBase Temperature: {base_temp}°F")
        print(f"Seasons: {', '.join(dd_data['seasons'])}")
        if hour_of_day is not None:
            print(f"Hour of Day: {hour_of_day}:00")
        else:
            print("Time Period: Daily average")

        analysis_df = dd_data['analysis_data']
        total_cdd = analysis_df['cdd'].sum()
        total_hdd = analysis_df['hdd'].sum()
        days_with_cdd = (analysis_df['cdd'] > 0).sum()
        days_with_hdd = (analysis_df['hdd'] > 0).sum()

        print(f"\nTotal Days Analyzed: {len(analysis_df)}")
        print(f"Total Cooling Degree Days: {total_cdd:.0f} ({days_with_cdd} days with cooling)")
        print(f"Total Heating Degree Days: {total_hdd:.0f} ({days_with_hdd} days with heating)")

        print("\n1. COOLING DEGREE DAY CORRELATION")
        print("-" * 70)
        print(f"   Correlation coefficient: {dd_data['cdd_correlation']:.3f}")
        if not np.isnan(dd_data['cdd_r_squared']):
            print(f"   R-squared: {dd_data['cdd_r_squared']:.3f}")
            print(f"   P-value: {dd_data['cdd_p_value']:.4f}")
            print(f"   Slope: {dd_data['cdd_slope']:.4f} {unit} per cooling degree day")
            print(f"   Baseload (intercept): {dd_data['cdd_intercept']:.2f} {unit}")

            print("\n   💡 INTERPRETATION:")
            if dd_data['cdd_r_squared'] > 0.7:
                print("      Strong relationship! Temperature is a major driver of AC usage")
            elif dd_data['cdd_r_squared'] > 0.5:
                print("      Good relationship - temperature explains most AC usage variation")
            elif dd_data['cdd_r_squared'] > 0.3:
                print("      Moderate relationship - other factors also affect AC usage")
            else:
                print("      Weak relationship - AC usage not strongly tied to temperature")

            if dd_data['cdd_slope'] > 0:
                cost_per_degree = dd_data['cdd_slope']
                print(f"      Each degree day above {base_temp}°F costs ~{cost_per_degree:.2f} {unit}")
                print(f"      A 10°F increase costs ~{cost_per_degree * 10:.2f} {unit}/day extra")
        else:
            print("   Insufficient data for cooling degree day analysis")

        print("\n2. HEATING DEGREE DAY CORRELATION")
        print("-" * 70)
        print(f"   Correlation coefficient: {dd_data['hdd_correlation']:.3f}")
        if not np.isnan(dd_data['hdd_r_squared']):
            print(f"   R-squared: {dd_data['hdd_r_squared']:.3f}")
            print(f"   P-value: {dd_data['hdd_p_value']:.4f}")
            print(f"   Slope: {dd_data['hdd_slope']:.4f} {unit} per heating degree day")
            print(f"   Baseload (intercept): {dd_data['hdd_intercept']:.2f} {unit}")

            print("\n   💡 INTERPRETATION:")
            if dd_data['hdd_r_squared'] > 0.7:
                print("      Strong relationship! Temperature is a major driver of heating usage")
            elif dd_data['hdd_r_squared'] > 0.5:
                print("      Good relationship - temperature explains most heating variation")
            elif dd_data['hdd_r_squared'] > 0.3:
                print("      Moderate relationship - other factors also affect heating")
            else:
                print("      Weak relationship - heating not strongly tied to temperature")

            if dd_data['hdd_slope'] > 0:
                cost_per_degree = dd_data['hdd_slope']
                print(f"      Each degree day below {base_temp}°F costs ~{cost_per_degree:.2f} {unit}")
                print(f"      A 10°F decrease costs ~{cost_per_degree * 10:.2f} {unit}/day extra")
        else:
            print("   Insufficient data for heating degree day analysis")

        print("\n" + "=" * 70)

    def print_weather_insights(self, weather_df: Optional[pd.DataFrame] = None):
        """Print weather correlation insights"""
        correlation_data = self.calculate_weather_correlation(weather_df)

        print("\n" + "=" * 70)
        print("WEATHER CORRELATION ANALYSIS")
        print("=" * 70)

        print("\n1. TEMPERATURE CORRELATION")
        print("-" * 70)
        temp_corr = correlation_data['temperature_correlation']
        temp_r2 = correlation_data['temperature_r_squared']
        print(f"   Correlation coefficient: {temp_corr:.3f}")
        print(f"   R-squared: {temp_r2:.3f}")
        print(f"   P-value: {correlation_data['temperature_p_value']:.4f}")
        print(f"   Slope: {correlation_data['temperature_slope']:.4f} kWH per °F")

        print("\n   💡 INTERPRETATION:")
        if abs(temp_corr) > 0.7:
            print(f"      {'Strong' if temp_corr > 0 else 'Strong negative'} correlation!")
        elif abs(temp_corr) > 0.4:
            print(f"      {'Moderate' if temp_corr > 0 else 'Moderate negative'} correlation")
        else:
            print("      Weak correlation")

        if temp_corr > 0.5:
            print("      Higher temps = more energy (likely AC)")
        elif temp_corr < -0.5:
            print("      Lower temps = more energy (likely heating)")

        print("\n2. HUMIDITY CORRELATION")
        print("-" * 70)
        rh_corr = correlation_data['humidity_correlation']
        rh_r2 = correlation_data['humidity_r_squared']
        print(f"   Correlation coefficient: {rh_corr:.3f}")
        print(f"   R-squared: {rh_r2:.3f}")
        print(f"   P-value: {correlation_data['humidity_p_value']:.4f}")
        print(f"   Slope: {correlation_data['humidity_slope']:.4f} kWH per % RH")

        print("\n   💡 INTERPRETATION:")
        if abs(rh_corr) > 0.5:
            print(f"      {'Moderate' if rh_corr > 0 else 'Moderate negative'} correlation")
            if rh_corr > 0:
                print("      Higher humidity = more energy (AC works harder in humid conditions)")
        else:
            print("      Weak correlation (expected - temp is main driver)")

        print("\n" + "=" * 70)


def main():
    """Example usage"""
    # Initialize the parser
    parser = EnergyUsageParser("Energy Usage.xml")

    # Parse the file
    data = parser.parse()

    # Print summary
    parser.print_summary()

    # Convert to DataFrame for analysis
    df = parser.to_dataframe()
    print("\n" + "=" * 60)
    print("DATAFRAME INFO")
    print("=" * 60)
    print(df.info())
    print("\n")
    print(df.head(10))

    # Get daily averages
    print("\n" + "=" * 60)
    print("DAILY AVERAGES")
    print("=" * 60)
    daily_avg = parser.get_daily_averages()
    print(daily_avg.head(10))

    # Get daily maximums
    print("\n" + "=" * 60)
    print("DAILY MAXIMUMS")
    print("=" * 60)
    daily_max = parser.get_daily_maximums()
    print(daily_max.head(10))

    # Plot daily averages
    print("\nGenerating daily average plot...")
    parser.plot_daily_averages(save_path='daily_energy_usage_avg.png')

    # Plot daily maximums
    print("\nGenerating daily maximum plot...")
    parser.plot_daily_maximums(save_path='daily_energy_usage_max.png')

    # Plot comparison
    print("\nGenerating comparison plot...")
    parser.plot_daily_comparison(save_path='daily_energy_usage_comparison.png')

    # Get hourly averages (diurnal pattern)
    print("\n" + "=" * 60)
    print("HOURLY AVERAGES (DIURNAL PATTERN)")
    print("=" * 60)
    hourly_avg = parser.get_hourly_averages()
    print(hourly_avg)

    # Plot diurnal pattern
    print("\nGenerating diurnal pattern plot...")
    parser.plot_diurnal_pattern(save_path='diurnal_energy_pattern.png')

    # Print energy conservation insights
    parser.print_energy_insights()

    # Fetch weather data and analyze correlations
    print("\n" + "=" * 60)
    print("FETCHING WEATHER DATA")
    print("=" * 60)
    try:
        weather_df = parser.fetch_weather_data(latitude=35.9101, longitude=-79.0753)  # Carrboro, NC

        # Print weather correlation insights
        parser.print_weather_insights(weather_df)

        # Plot weather correlations
        print("\nGenerating weather correlation plots...")
        parser.plot_weather_correlation(weather_df, save_path='energy_weather_correlation.png')

        # Plot energy vs temperature time series
        print("\nGenerating energy vs temperature time series...")
        parser.plot_energy_weather_timeseries(weather_df, save_path='energy_temperature_timeseries.png')

        # Degree day analysis - all seasons
        print("\n" + "=" * 60)
        print("DEGREE DAY ANALYSIS (ALL SEASONS)")
        print("=" * 60)
        parser.print_degree_day_insights(weather_df)
        parser.plot_degree_day_correlation(weather_df, save_path='degree_days_all_seasons.png')

        # Degree day analysis - summer only (for cooling)
        print("\n" + "=" * 60)
        print("DEGREE DAY ANALYSIS (SUMMER - COOLING FOCUS)")
        print("=" * 60)
        parser.print_degree_day_insights(weather_df, seasons=['summer'])
        parser.plot_degree_day_correlation(weather_df, seasons=['summer'],
                                          save_path='degree_days_summer.png')

        # Degree day analysis - winter only (for heating)
        print("\n" + "=" * 60)
        print("DEGREE DAY ANALYSIS (WINTER - HEATING FOCUS)")
        print("=" * 60)
        parser.print_degree_day_insights(weather_df, seasons=['winter'])
        parser.plot_degree_day_correlation(weather_df, seasons=['winter'],
                                          save_path='degree_days_winter.png')

        # Example: Peak hour analysis (5 PM)
        print("\n" + "=" * 60)
        print("DEGREE DAY ANALYSIS (5 PM HOUR - PEAK TIME)")
        print("=" * 60)
        parser.print_degree_day_insights(weather_df, hour_of_day=17)
        parser.plot_degree_day_correlation(weather_df, hour_of_day=17,
                                          save_path='degree_days_5pm.png')

    except Exception as e:
        print(f"Unable to fetch weather data: {e}")
        print("Continuing without weather analysis...")

    # Save to CSV if desired
    # df.to_csv('energy_usage_parsed.csv')
    # daily_avg.to_csv('daily_energy_averages.csv')
    # daily_max.to_csv('daily_energy_maximums.csv')
    # hourly_avg.to_csv('hourly_energy_averages.csv')


if __name__ == "__main__":
    main()
