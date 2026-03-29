import logging
import anthropic
from ecommerce import config

log = logging.getLogger(__name__)


def generate_listing_copy(product, marketplace, competitor_listings=None):
    """
    Use Claude to generate listing title, description, and bullet points.

    Args:
        product: dict with Manufacturer, Model, Colour, Grade, Quantity
        marketplace: 'Amazon' or 'eBay'
        competitor_listings: optional list of competitor listing texts for reference

    Returns:
        dict with 'title', 'description', 'bullets', 'condition_note'
    """
    competitor_context = ""
    if competitor_listings:
        competitor_context = "\n\nHere are top competitor listings for reference:\n"
        for i, listing in enumerate(competitor_listings, 1):
            competitor_context += f"\n--- Competitor {i} ---\n{listing}\n"

    prompt = f"""Generate an ecommerce listing for the following product on {marketplace}:

Manufacturer: {product['Manufacturer']}
Model: {product['Model']}
Colour: {product['Colour']}
Grade: {product['Grade']}
Quantity available: {product['Quantity']}
{competitor_context}

Generate the following in JSON format:
{{
    "title": "A compelling listing title (max 80 chars)",
    "description": "A professional product description (2-3 sentences)",
    "bullets": ["bullet point 1", "bullet point 2", "bullet point 3", "bullet point 4", "bullet point 5"],
    "condition_note": "A brief condition description based on the grade"
}}

Rules:
- Be professional and accurate — do not exaggerate condition
- Include the manufacturer, model, colour, and storage in the title
- Mention the grade-appropriate condition clearly
- For Grade A: Like New / Excellent condition
- For Grade B: Very Good condition, minor cosmetic wear
- For Grade C: Good condition, visible cosmetic wear
- Return ONLY the JSON object, no other text"""

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    response_text = message.content[0].text.strip()

    import json
    try:
        return json.loads(response_text)
    except json.JSONDecodeError:
        # Try to extract JSON from the response if wrapped in markdown
        if '```' in response_text:
            json_str = response_text.split('```')[1]
            if json_str.startswith('json'):
                json_str = json_str[4:]
            return json.loads(json_str.strip())
        log.error("Failed to parse listing copy response: %s", response_text)
        raise
