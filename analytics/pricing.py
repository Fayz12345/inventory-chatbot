def _safe_float(value, default=0.0):
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _lookup_price_by_grade(pricing_row, grade):
    if not pricing_row or not grade:
        return 0.0
    grade = grade.strip().upper()
    return {
        'A': pricing_row['grade_a'],
        'B': pricing_row['grade_b'],
        'C': pricing_row['grade_c'],
    }.get(grade, 0.0)


def compute_report(devices, pricing_map):
    enriched = []

    for dev in devices:
        model_key = (dev.get('ModelVerb') or '').strip().lower()
        pricing = pricing_map.get(model_key)

        conditions = (dev.get('Conditions') or '').strip()
        received_grade = (dev.get('Received_Grade') or '').strip()
        post_repair_grade = (dev.get('Post-Repair_Grade') or '').strip()
        grade_improvement = (dev.get('Grade_Improvement') or '').strip()
        post_improved_grade = (dev.get('Post_Improved_Grade') or '').strip()

        device_type = pricing['device_type'] if pricing else 'Phone'
        is_modem = device_type.lower() == 'modem'

        # --- Unassessed price (Excel col L) ---
        if not pricing:
            unassessed_price = 0.0
            pricing_error = 'Model not in pricing master'
        elif is_modem:
            unassessed_price = 0.0
            pricing_error = None
        elif conditions.lower() == 'defective':
            unassessed_price = pricing['defective']
            pricing_error = None
        elif conditions.lower() == 'frp':
            frp_val = pricing['frp']
            unassessed_price = frp_val if frp_val != 0 else None
            pricing_error = None
        else:
            unassessed_price = pricing['grade_c']
            pricing_error = None

        # --- Assessed price (Excel col N) ---
        if not pricing:
            assessed_price = 0.0
        elif is_modem:
            assessed_price = pricing['grade_c']
        elif conditions.lower() == 'defective':
            assessed_price = pricing['defective']
        elif conditions.lower() == 'frp':
            assessed_price = pricing['frp']
        elif 'new' in conditions.lower():
            assessed_price = pricing['grade_a']
        else:
            assessed_price = _lookup_price_by_grade(pricing, received_grade)

        # --- Repair costs (Excel cols U, W, X) ---
        labour_cost = _safe_float(dev.get('T_Level_Cost'))
        parts_cost = _safe_float(dev.get('T_Part_Cost'))
        total_repair_cost = labour_cost + parts_cost

        price_after_repair = _lookup_price_by_grade(pricing, post_repair_grade)

        if conditions.lower() in ('defective', 'frp'):
            ua = _safe_float(unassessed_price)
            upside = price_after_repair - total_repair_cost - ua
        else:
            upside = None

        # --- Improvement costs (Excel cols AB, AD, AE, AF) ---
        imp_labour = _safe_float(dev.get('T_Level_Improved_Cos'))
        imp_parts = _safe_float(dev.get('T_Part_Improved_Cost'))
        total_improvement_cost = imp_labour + imp_parts
        total_repair_plus_improvement = total_repair_cost + total_improvement_cost

        if pricing and post_improved_grade.upper() == 'A':
            price_after_improvement = pricing['grade_a']
        else:
            price_after_improvement = 0.0

        if grade_improvement.lower() == 'yes':
            ua = _safe_float(unassessed_price)
            improvement_upside = (price_after_improvement
                                  - total_repair_plus_improvement - ua)
        else:
            improvement_upside = None

        # --- Recommendation (Excel col AG) ---
        if conditions.lower() in ('defective', 'frp'):
            if upside is not None and upside > 0:
                recommendation = 'Sell After Repair'
            else:
                recommendation = 'Sell As Is'
        elif conditions.lower() in ('nyt', 'nyt - not yet tested'):
            recommendation = 'Sell As Is'
        else:
            if improvement_upside is not None and improvement_upside > 0:
                recommendation = 'Sell After Grade Improvement'
            else:
                recommendation = 'Sell As Functional'

        # --- Lot value (Excel col AH) ---
        if conditions.lower() in ('defective', 'frp'):
            if upside is not None and upside > 0:
                lot_value = price_after_repair
            else:
                lot_value = _safe_float(unassessed_price)
        elif conditions.lower() in ('nyt', 'nyt - not yet tested'):
            lot_value = _safe_float(assessed_price)
        else:
            if improvement_upside is not None and improvement_upside > 0:
                lot_value = (price_after_improvement
                             - total_repair_plus_improvement)
            else:
                lot_value = assessed_price

        row = dict(dev)
        row.update({
            'unassessed_price': unassessed_price,
            'assessed_price': assessed_price,
            'total_repair_cost': total_repair_cost,
            'price_after_repair': price_after_repair,
            'upside': upside,
            'total_improvement_cost': total_improvement_cost,
            'total_repair_plus_improvement': total_repair_plus_improvement,
            'price_after_improvement': price_after_improvement,
            'improvement_upside': improvement_upside,
            'recommendation': recommendation,
            'lot_value': lot_value,
            'pricing_error': pricing_error,
        })
        enriched.append(row)

    summary = _build_summary(enriched)
    return enriched, summary


def _build_summary(rows):
    total = len(rows)
    conditions = {}
    recommendations = {}
    total_lot_value = 0.0
    unpriced_models = {}

    for r in rows:
        cond = r.get('Conditions') or 'Unknown'
        conditions[cond] = conditions.get(cond, 0) + 1
        rec = r.get('recommendation', 'Unknown')
        recommendations[rec] = recommendations.get(rec, 0) + 1
        total_lot_value += _safe_float(r.get('lot_value'))
        if r.get('pricing_error'):
            model = r.get('ModelVerb') or 'Unknown'
            unpriced_models[model] = unpriced_models.get(model, 0) + 1

    return {
        'total_devices': total,
        'conditions_breakdown': conditions,
        'recommendation_breakdown': recommendations,
        'total_lot_value': round(total_lot_value, 2),
        'unpriced_models': unpriced_models,
    }
