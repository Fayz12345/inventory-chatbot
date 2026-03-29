import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Template
from ecommerce import config

log = logging.getLogger(__name__)

EMAIL_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
<head>
<style>
    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
    .container { max-width: 900px; margin: 0 auto; background: #fff; border-radius: 8px; padding: 30px; }
    h1 { color: #333; border-bottom: 2px solid #2196F3; padding-bottom: 10px; }
    h2 { color: #555; margin-top: 30px; }
    table { width: 100%; border-collapse: collapse; margin: 15px 0; }
    th { background: #2196F3; color: #fff; padding: 12px 10px; text-align: left; font-size: 13px; }
    td { padding: 10px; border-bottom: 1px solid #eee; font-size: 13px; }
    tr:hover { background: #f9f9f9; }
    .price { font-weight: bold; color: #2e7d32; }
    .skip { color: #c62828; }
    .btn { display: inline-block; padding: 6px 16px; border-radius: 4px; text-decoration: none;
           font-size: 12px; font-weight: bold; margin-right: 5px; }
    .btn-approve { background: #4CAF50; color: #fff; }
    .btn-reject { background: #f44336; color: #fff; }
    .summary { background: #e3f2fd; padding: 15px; border-radius: 6px; margin-bottom: 20px; }
    .footer { margin-top: 30px; font-size: 12px; color: #999; border-top: 1px solid #eee; padding-top: 15px; }
</style>
</head>
<body>
<div class="container">
    <h1>Ecommerce Daily Digest</h1>

    <div class="summary">
        <strong>{{ recommendations | length }}</strong> SKUs scanned &mdash;
        <strong>{{ recommendations | selectattr('margin_ok') | list | length }}</strong> recommended,
        <strong>{{ recommendations | rejectattr('margin_ok') | list | length }}</strong> skipped
    </div>

    {% set recommended = recommendations | selectattr('margin_ok') | list %}
    {% if recommended %}
    <h2>Recommended Listings</h2>
    <table>
        <tr>
            <th>Product</th>
            <th>Qty</th>
            <th>Marketplace</th>
            <th>Price</th>
            <th>Amazon Floor</th>
            <th>eBay Floor</th>
            <th>Cost</th>
            <th>Action</th>
        </tr>
        {% for rec in recommended %}
        <tr>
            <td>{{ rec.product.Manufacturer }} {{ rec.product.Model }}<br>
                <small>{{ rec.product.Colour }} / Grade {{ rec.product.Grade }}</small></td>
            <td>{{ rec.product.Quantity }}</td>
            <td><strong>{{ rec.marketplace }}</strong></td>
            <td class="price">${{ "%.2f" | format(rec.price) }}</td>
            <td>{{ "$%.2f" | format(rec.amazon_price) if rec.amazon_price else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.ebay_price) if rec.ebay_price else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.device_cost) if rec.device_cost else "N/A" }}</td>
            <td>
                <a href="{{ base_url }}/ecommerce/approve?idx={{ loop.index0 }}&token={{ token }}" class="btn btn-approve">Approve</a>
                <a href="{{ base_url }}/ecommerce/reject?idx={{ loop.index0 }}&token={{ token }}" class="btn btn-reject">Reject</a>
            </td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% set skipped = recommendations | rejectattr('margin_ok') | list %}
    {% if skipped %}
    <h2>Skipped (Margin / Data Issues)</h2>
    <table>
        <tr>
            <th>Product</th>
            <th>Qty</th>
            <th>Reason</th>
            <th>Amazon Floor</th>
            <th>eBay Floor</th>
            <th>Cost</th>
        </tr>
        {% for rec in skipped %}
        <tr>
            <td>{{ rec.product.Manufacturer }} {{ rec.product.Model }}<br>
                <small>{{ rec.product.Colour }} / Grade {{ rec.product.Grade }}</small></td>
            <td>{{ rec.product.Quantity }}</td>
            <td class="skip">{{ rec.skip_reason }}</td>
            <td>{{ "$%.2f" | format(rec.amazon_price) if rec.amazon_price else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.ebay_price) if rec.ebay_price else "N/A" }}</td>
            <td>{{ "$%.2f" | format(rec.device_cost) if rec.device_cost else "N/A" }}</td>
        </tr>
        {% endfor %}
    </table>
    {% endif %}

    {% if not recommendations %}
    <p>No new products to list today. All Ecommerce Storefront SKUs already have active listings.</p>
    {% endif %}

    <div class="footer">
        Generated automatically by the Ecommerce AI Pipeline.<br>
        Approve/reject links are single-use and expire after 48 hours.
    </div>
</div>
</body>
</html>
""")


def build_digest_html(recommendations, approval_token):
    """Render the email digest HTML from a list of recommendation dicts."""
    return EMAIL_TEMPLATE.render(
        recommendations=recommendations,
        base_url=config.APP_BASE_URL,
        token=approval_token,
    )


def send_digest(recommendations, approval_token):
    """Build and send the daily ecommerce digest email."""
    if not config.SMTP_HOST or not config.EMAIL_TO:
        log.warning("SMTP not configured — printing digest to log instead")
        html = build_digest_html(recommendations, approval_token)
        log.info("Email digest (not sent):\n%s", html)
        return False

    html = build_digest_html(recommendations, approval_token)

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f'Ecommerce Daily Digest — {len(recommendations)} SKUs'
    msg['From'] = config.EMAIL_FROM
    msg['To'] = config.EMAIL_TO
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as server:
            server.starttls()
            server.login(config.SMTP_USER, config.SMTP_PASSWORD)
            server.sendmail(config.EMAIL_FROM, [config.EMAIL_TO], msg.as_string())
        log.info("Digest email sent to %s", config.EMAIL_TO)
        return True
    except Exception as e:
        log.error("Failed to send digest email: %s", e)
        return False
