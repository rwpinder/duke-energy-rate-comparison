"""
Flask Web Application for Duke Energy Rate Comparison
"""

from flask import Flask, render_template, request, jsonify
import os
import xml.etree.ElementTree as ET
from werkzeug.utils import secure_filename
from energy_usage import EnergyUsageParser
from rate_comparison import DukeEnergyRateCalculator
import pandas as pd

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@app.route('/')
def index():
    """Render the main upload page"""
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle file upload and process rate comparison"""

    # Check if file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    # Validate file type
    if not file.filename.endswith('.xml'):
        return jsonify({'error': 'Invalid file type. Please upload an XML file from Duke Energy Green Button'}), 400

    # Save and process the file
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        file.save(filepath)

        # Parse the energy data
        parser = EnergyUsageParser(filepath)
        data = parser.parse()
        energy_df = parser.to_dataframe()

        # Validate that we have data
        if energy_df is None or len(energy_df) == 0:
            raise ValueError("No energy usage data found in the XML file. Please ensure you've uploaded a valid Duke Energy Green Button file.")

        if len(energy_df) < 48:  # Less than 1 day of data (48 half-hour intervals)
            raise ValueError(f"Insufficient data: only {len(energy_df)} readings found. Need at least 1 day of usage data for analysis.")

        # Calculate rates
        calculator = DukeEnergyRateCalculator()
        standard_costs, tou_costs, tou_ev_costs, comparison, comparison_all = \
            calculator.compare_rates(energy_df)

        # Calculate totals
        total_standard = float(standard_costs['total_cost'].sum())
        total_tou = float(tou_costs['total_cost'].sum())
        total_tou_ev = float(tou_ev_costs['total_cost'].sum())

        tou_savings = total_standard - total_tou
        tou_ev_savings = total_standard - total_tou_ev
        tou_ev_vs_tou_savings = total_tou - total_tou_ev

        # Determine best rate
        rates = [
            ('Standard', total_standard),
            ('TOU', total_tou),
            ('TOU-EV', total_tou_ev)
        ]
        best_rate_name, best_rate_cost = min(rates, key=lambda x: x[1])

        # Calculate usage breakdown for TOU
        avg_on_peak = float(tou_costs['on_peak_kwh'].mean())
        avg_off_peak = float(tou_costs['off_peak_kwh'].mean())
        avg_discount = float(tou_costs['discount_kwh'].mean())
        total_avg = avg_on_peak + avg_off_peak + avg_discount

        on_peak_pct = (avg_on_peak / total_avg * 100) if total_avg > 0 else 0
        off_peak_pct = (avg_off_peak / total_avg * 100) if total_avg > 0 else 0
        discount_pct = (avg_discount / total_avg * 100) if total_avg > 0 else 0

        # Calculate usage breakdown for TOU-EV
        avg_ev_discount = float(tou_ev_costs['discount_kwh'].mean())
        avg_ev_standard = float(tou_ev_costs['standard_kwh'].mean())
        total_ev_avg = avg_ev_discount + avg_ev_standard

        ev_discount_pct = (avg_ev_discount / total_ev_avg * 100) if total_ev_avg > 0 else 0
        ev_standard_pct = (avg_ev_standard / total_ev_avg * 100) if total_ev_avg > 0 else 0

        # Average demand charges for TOU
        avg_demand_charge = float(tou_costs['demand_charge'].mean())

        # Convert monthly data to JSON-friendly format
        monthly_data = []
        for _, row in comparison_all.iterrows():
            monthly_data.append({
                'month': row['month'].strftime('%Y-%m'),
                'standard_cost': float(row['standard_cost']),
                'tou_cost': float(row['tou_cost']),
                'tou_ev_cost': float(row['tou_ev_cost'])
            })

        # Prepare comprehensive results
        results = {
            'success': True,
            'totals': {
                'standard': total_standard,
                'tou': total_tou,
                'tou_ev': total_tou_ev
            },
            'savings': {
                'tou': tou_savings,
                'tou_ev': tou_ev_savings,
                'tou_ev_vs_tou': tou_ev_vs_tou_savings
            },
            'percentages': {
                'tou': (tou_savings / total_standard * 100) if total_standard > 0 else 0,
                'tou_ev': (tou_ev_savings / total_standard * 100) if total_standard > 0 else 0
            },
            'best_rate': {
                'name': best_rate_name,
                'cost': best_rate_cost
            },
            'usage_breakdown': {
                'tou': {
                    'on_peak_kwh': avg_on_peak,
                    'off_peak_kwh': avg_off_peak,
                    'discount_kwh': avg_discount,
                    'on_peak_pct': on_peak_pct,
                    'off_peak_pct': off_peak_pct,
                    'discount_pct': discount_pct,
                    'avg_demand_charge': avg_demand_charge
                },
                'tou_ev': {
                    'discount_kwh': avg_ev_discount,
                    'standard_kwh': avg_ev_standard,
                    'discount_pct': ev_discount_pct,
                    'standard_pct': ev_standard_pct
                }
            },
            'monthly_data': monthly_data
        }

        # Clean up uploaded file
        os.remove(filepath)

        return jsonify(results)

    except ValueError as e:
        # Clean up file if it exists
        if os.path.exists(filepath):
            os.remove(filepath)

        # Return user-friendly validation error
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400

    except KeyError as e:
        # Clean up file if it exists
        if os.path.exists(filepath):
            os.remove(filepath)

        # Missing expected data in XML
        return jsonify({
            'success': False,
            'error': f'Invalid Green Button file format: Missing required field {str(e)}. Please ensure you downloaded the file correctly from Duke Energy.'
        }), 400

    except ET.ParseError as e:
        # Clean up file if it exists
        if os.path.exists(filepath):
            os.remove(filepath)

        # XML parsing error
        return jsonify({
            'success': False,
            'error': 'Invalid XML file format. The file appears to be corrupted or not a valid XML file. Please download a fresh copy from Duke Energy.'
        }), 400

    except Exception as e:
        # Clean up file if it exists
        if os.path.exists(filepath):
            os.remove(filepath)

        # Generic error with more helpful message
        error_msg = str(e)

        # Provide more context for common errors
        if 'not found' in error_msg.lower():
            error_msg = 'Required data not found in the XML file. Please ensure this is a Duke Energy Green Button export file.'
        elif 'parse' in error_msg.lower():
            error_msg = 'Unable to parse the XML file. Please ensure you uploaded a valid Green Button file from Duke Energy.'
        else:
            error_msg = f'Unexpected error processing file: {error_msg}. Please ensure you uploaded a valid Duke Energy Green Button XML file.'

        return jsonify({
            'success': False,
            'error': error_msg
        }), 500


if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("Duke Energy Rate Comparison Tool")
    print("=" * 70)
    print("\nStarting Flask web server...")
    print("Open your browser and go to: http://localhost:5000")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 70 + "\n")

    app.run(debug=True, port=5000)
