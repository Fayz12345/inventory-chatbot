import pyodbc
from analytics import config


def get_db_connection():
    conn = pyodbc.connect(
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={config.DB_SERVER};"
        f"DATABASE={config.DB_NAME};"
        f"UID={config.DB_USER};"
        f"PWD={config.DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    return conn


# ---------------------------------------------------------------------------
# Stored procedure — Telus Weekly repair assessment
# ---------------------------------------------------------------------------

def call_repair_assessment(project_tag, client_name=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "EXEC dbo.GetReport_RepairAssessment_ByProjectTag "
        "@ProjectTag=?, @ClientName=?",
        (project_tag, client_name),
    )
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Pricing master — CRUD
# ---------------------------------------------------------------------------

def get_pricing_map():
    sql = """
        SELECT LTRIM(RTRIM(Model)) AS Model,
               GradeA_Price, GradeB_Price, GradeC_Price,
               Defective_Price, FRP_Price, DeviceType
        FROM TelusWeeklyPricingMaster
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return {
        row['Model'].lower(): {
            'grade_a': float(row['GradeA_Price'] or 0),
            'grade_b': float(row['GradeB_Price'] or 0),
            'grade_c': float(row['GradeC_Price'] or 0),
            'defective': float(row['Defective_Price'] or 0),
            'frp': float(row['FRP_Price'] or 0),
            'device_type': (row['DeviceType'] or 'Phone').strip(),
        }
        for row in rows
    }


def get_all_pricing_models():
    sql = """
        SELECT ID, Model, GradeA_Price, GradeB_Price, GradeC_Price,
               Defective_Price, FRP_Price, DeviceType, UpdatedAt, UpdatedBy
        FROM TelusWeeklyPricingMaster
        ORDER BY Model
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql)
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def bulk_update_pricing(updates, updated_by=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = """
        UPDATE TelusWeeklyPricingMaster
        SET GradeA_Price = ?, GradeB_Price = ?, GradeC_Price = ?,
            Defective_Price = ?, FRP_Price = ?, DeviceType = ?,
            UpdatedAt = GETDATE(), UpdatedBy = ?
        WHERE ID = ?
    """
    for u in updates:
        cursor.execute(sql, (
            u['grade_a'], u['grade_b'], u['grade_c'],
            u['defective'], u['frp'], u['device_type'],
            updated_by, u['id'],
        ))
    conn.commit()
    conn.close()


def insert_pricing_model(model, grade_a, grade_b, grade_c,
                         defective, frp, device_type):
    sql = """
        INSERT INTO TelusWeeklyPricingMaster
            (Model, GradeA_Price, GradeB_Price, GradeC_Price,
             Defective_Price, FRP_Price, DeviceType)
        OUTPUT INSERTED.ID
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(sql, (model, grade_a, grade_b, grade_c,
                         defective, frp, device_type))
    new_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return int(new_id)


def get_distinct_models_for_project(project_tag, client_name=None):
    devices = call_repair_assessment(project_tag, client_name)
    model_counts = {}
    for d in devices:
        mv = (d.get('ModelVerb') or '').strip()
        if mv:
            model_counts[mv] = model_counts.get(mv, 0) + 1
    return model_counts


def get_pricing_models_by_names(model_names):
    if not model_names:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    placeholders = ','.join(['?' for _ in model_names])
    sql = f"""
        SELECT ID, LTRIM(RTRIM(Model)) AS Model, GradeA_Price, GradeB_Price,
               GradeC_Price, Defective_Price, FRP_Price, DeviceType,
               UpdatedAt, UpdatedBy
        FROM TelusWeeklyPricingMaster
        WHERE LOWER(LTRIM(RTRIM(Model))) IN ({placeholders})
        ORDER BY Model
    """
    cursor.execute(sql, [m.lower() for m in model_names])
    columns = [col[0] for col in cursor.description]
    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
    conn.close()
    return rows


def bulk_insert_pricing_models(models):
    if not models:
        return []
    conn = get_db_connection()
    cursor = conn.cursor()
    sql = """
        INSERT INTO TelusWeeklyPricingMaster
            (Model, GradeA_Price, GradeB_Price, GradeC_Price,
             Defective_Price, FRP_Price, DeviceType)
        OUTPUT INSERTED.ID
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """
    new_ids = []
    for m in models:
        cursor.execute(sql, (
            m['model'], m.get('grade_a', 0), m.get('grade_b', 0),
            m.get('grade_c', 0), m.get('defective', 0), m.get('frp', 0),
            m.get('device_type', 'Phone'),
        ))
        new_ids.append(cursor.fetchone()[0])
    conn.commit()
    conn.close()
    return new_ids


def delete_pricing_model(model_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM TelusWeeklyPricingMaster WHERE ID = ?",
                   (model_id,))
    conn.commit()
    conn.close()
