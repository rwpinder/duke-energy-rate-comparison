// Duke Energy Rate Comparison Tool - JavaScript

// Handle file selection
document.getElementById('fileInput').addEventListener('change', function(e) {
    const fileName = e.target.files[0]?.name || 'No file selected';
    document.getElementById('fileName').textContent = fileName;

    // Enable analyze button if file is selected
    const analyzeBtn = document.getElementById('analyzeBtn');
    analyzeBtn.disabled = !e.target.files[0];
});

// Upload and process file
async function uploadFile() {
    const fileInput = document.getElementById('fileInput');
    const file = fileInput.files[0];

    if (!file) {
        showError('Please select a file');
        return;
    }

    // Hide previous results and errors
    document.getElementById('results').style.display = 'none';
    document.getElementById('errorMessage').style.display = 'none';

    // Show loading indicator
    document.getElementById('loading').style.display = 'block';

    // Create form data
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (response.ok && data.success) {
            displayResults(data);
        } else {
            showError(data.error || 'Error processing file');
        }
    } catch (error) {
        showError('Network error: ' + error.message);
    } finally {
        document.getElementById('loading').style.display = 'none';
    }
}

// Display error message
function showError(message) {
    const errorDiv = document.getElementById('errorMessage');
    errorDiv.textContent = message;
    errorDiv.style.display = 'block';
}

// Format currency
function formatCurrency(amount) {
    return '$' + amount.toFixed(2);
}

// Format percentage
function formatPercent(percent) {
    return percent.toFixed(1) + '%';
}

// Display results
function displayResults(data) {
    const resultsDiv = document.getElementById('results');

    const bestRate = data.best_rate.name;
    const totals = data.totals;
    const savings = data.savings;
    const percentages = data.percentages;
    const usage = data.usage_breakdown;

    let html = `
        <div class="result-header">
            <h2>Your Rate Comparison Results</h2>
        </div>

        <div class="best-rate-banner">
            <h3>★ Best Rate: ${bestRate}</h3>
            <p style="font-size: 1.5em; margin-top: 10px;">${formatCurrency(data.best_rate.cost)}/year</p>
        </div>

        <div class="rate-cards">
            <div class="rate-card ${bestRate === 'Standard' ? 'best' : ''}">
                <h3>Standard Rate (RES)</h3>
                <div class="cost">${formatCurrency(totals.standard)}</div>
                <p>Traditional tiered pricing</p>
                ${bestRate !== 'Standard' ? `<p class="loss">Baseline</p>` : '<p class="savings">✓ Best Option</p>'}
            </div>

            <div class="rate-card ${bestRate === 'TOU' ? 'best' : ''}">
                <h3>Time-of-Use (R-TOUD)</h3>
                <div class="cost">${formatCurrency(totals.tou)}</div>
                <p>Peak/off-peak + demand charges</p>
                ${savings.tou > 0 ?
                    `<p class="savings">Saves ${formatCurrency(savings.tou)} (${formatPercent(percentages.tou)})</p>` :
                    `<p class="loss">Costs ${formatCurrency(Math.abs(savings.tou))} more</p>`
                }
            </div>

            <div class="rate-card ${bestRate === 'TOU-EV' ? 'best' : ''}">
                <h3>TOU-EV (R-TOU-EV)</h3>
                <div class="cost">${formatCurrency(totals.tou_ev)}</div>
                <p>EV owners, overnight discount</p>
                ${savings.tou_ev > 0 ?
                    `<p class="savings">Saves ${formatCurrency(savings.tou_ev)} (${formatPercent(percentages.tou_ev)})</p>` :
                    `<p class="loss">Costs ${formatCurrency(Math.abs(savings.tou_ev))} more</p>`
                }
            </div>
        </div>
    `;

    // Add usage breakdown
    html += `
        <div class="usage-breakdown">
            <h3>Your Energy Usage Pattern</h3>

            <h4 style="margin-top: 20px; color: #4a5568;">Time-of-Use (R-TOUD) Breakdown:</h4>
            <div class="usage-item">
                <span class="usage-label">On-Peak Usage (expensive)</span>
                <span class="usage-value">${usage.tou.on_peak_kwh.toFixed(1)} kWh (${formatPercent(usage.tou.on_peak_pct)})</span>
            </div>
            <div class="usage-item">
                <span class="usage-label">Off-Peak Usage</span>
                <span class="usage-value">${usage.tou.off_peak_kwh.toFixed(1)} kWh (${formatPercent(usage.tou.off_peak_pct)})</span>
            </div>
            <div class="usage-item">
                <span class="usage-label">Discount Hours</span>
                <span class="usage-value">${usage.tou.discount_kwh.toFixed(1)} kWh (${formatPercent(usage.tou.discount_pct)})</span>
            </div>
            <div class="usage-item">
                <span class="usage-label">Avg. Demand Charges</span>
                <span class="usage-value">${formatCurrency(usage.tou.avg_demand_charge)}/month</span>
            </div>

            <h4 style="margin-top: 20px; color: #4a5568;">TOU-EV Breakdown:</h4>
            <div class="usage-item">
                <span class="usage-label">Discount (11 PM - 5 AM)</span>
                <span class="usage-value">${usage.tou_ev.discount_kwh.toFixed(1)} kWh (${formatPercent(usage.tou_ev.discount_pct)})</span>
            </div>
            <div class="usage-item">
                <span class="usage-label">Standard (all other hours)</span>
                <span class="usage-value">${usage.tou_ev.standard_kwh.toFixed(1)} kWh (${formatPercent(usage.tou_ev.standard_pct)})</span>
            </div>
            <div class="usage-item">
                <span class="usage-label">Demand Charges</span>
                <span class="usage-value">$0.00 (none!)</span>
            </div>
        </div>
    `;

    // Add recommendations
    html += generateRecommendations(data);

    // Add monthly breakdown table
    html += `
        <h3 style="margin-top: 40px; color: #2c3e50;">Monthly Cost Breakdown</h3>
        <div style="overflow-x: auto;">
            <table class="monthly-table">
                <thead>
                    <tr>
                        <th>Month</th>
                        <th>Standard</th>
                        <th>TOU</th>
                        <th>TOU-EV</th>
                        <th>Best</th>
                    </tr>
                </thead>
                <tbody>
    `;

    data.monthly_data.forEach(month => {
        const costs = [
            {name: 'Std', value: month.standard_cost},
            {name: 'TOU', value: month.tou_cost},
            {name: 'EV', value: month.tou_ev_cost}
        ];
        const best = costs.reduce((min, curr) => curr.value < min.value ? curr : min).name;

        html += `
            <tr>
                <td>${month.month}</td>
                <td>${formatCurrency(month.standard_cost)}</td>
                <td>${formatCurrency(month.tou_cost)}</td>
                <td>${formatCurrency(month.tou_ev_cost)}</td>
                <td><strong>${best}</strong></td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    resultsDiv.innerHTML = html;
    resultsDiv.style.display = 'block';

    // Scroll to results
    resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Generate recommendations based on results
function generateRecommendations(data) {
    const bestRate = data.best_rate.name;
    const savings = data.savings;
    const usage = data.usage_breakdown;

    let html = '<div class="recommendation"><h3>💡 Recommendations</h3>';

    if (bestRate === 'TOU-EV') {
        html += `
            <p><strong>★★★ STRONGLY RECOMMEND: Switch to TOU-EV Rate (R-TOU-EV)</strong></p>
            <ul>
                <li>Save ${formatCurrency(savings.tou_ev)}/year compared to Standard (${formatPercent(data.percentages.tou_ev)})</li>
        `;
        if (savings.tou_ev_vs_tou > 0) {
            html += `<li>Save ${formatCurrency(savings.tou_ev_vs_tou)}/year compared to regular TOU</li>`;
        }
        html += `
                <li>No demand charges (saves ~${formatCurrency(usage.tou.avg_demand_charge)}/month)</li>
                <li>Simple rate with long discount window (11 PM - 5 AM)</li>
                <li>You currently use ${formatPercent(usage.tou_ev.discount_pct)} during discount hours</li>
            </ul>
            <p style="margin-top: 15px;"><strong>Next Steps:</strong></p>
            <ul>
                <li>Contact Duke Energy to switch to R-TOU-EV</li>
                <li>Provide proof of EV ownership/lease</li>
                <li>⚠️ Pilot limited to 20,000 customers - enroll soon!</li>
            </ul>
        `;
    } else if (bestRate === 'TOU') {
        html += `
            <p><strong>✓ RECOMMEND: Time-of-Use Rate (R-TOUD)</strong></p>
            <ul>
                <li>Save ${formatCurrency(savings.tou)}/year compared to Standard (${formatPercent(data.percentages.tou)})</li>
                <li>You use only ${formatPercent(usage.tou.on_peak_pct)} during expensive on-peak hours</li>
        `;
        if (savings.tou_ev > savings.tou) {
            html += `
                <li>Note: TOU-EV would save even more (${formatCurrency(savings.tou_ev)}/year total)</li>
                <li>Consider TOU-EV if you own or lease an electric vehicle</li>
            `;
        }
        html += `
            </ul>
        `;
    } else {
        html += `
            <p><strong>Standard rate is currently cheapest for your usage pattern</strong></p>
            <ul>
                <li>You use ${formatPercent(usage.tou.on_peak_pct)} during TOU on-peak hours</li>
                <li>You use ${formatPercent(usage.tou_ev.discount_pct)} during TOU-EV discount hours (11 PM - 5 AM)</li>
            </ul>
            <p style="margin-top: 15px;"><strong>To benefit from TOU rates:</strong></p>
            <ul>
                <li>Shift more usage to overnight hours (11 PM - 5 AM) - only 6.548¢/kWh</li>
                <li>Avoid peak hours (6-9 PM summer, 6-9 AM winter on weekdays)</li>
                <li>Use timers for water heater, dishwasher, laundry</li>
            </ul>
        `;
    }

    html += '</div>';
    return html;
}
