from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from supabase import create_client
from collections import defaultdict

import io

app = Flask(__name__)
CORS(app)

# ============================================
# ΣΤΟΙΧΕΙΑ SUPABASE (ΒΑΛΕ ΤΑ ΔΙΚΑ ΣΟΥ)
# ============================================
SUPABASE_URL = "https://hjfbcknlnvgwsfqhfxwx.supabase.co"
SUPABASE_KEY = "sb_publishable_YOlkfQYde0xMkRHe5QOASA_iHLiOBVD"
# ============================================

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
print("✅ Backend συνδέθηκε στο Supabase")

# ============================================
# 1. LATEST READINGS (τελευταία μη-μηδενική τιμή)
# ============================================
@app.route('/api/latest', methods=['GET'])
def get_latest():
    location_param = request.args.get('location', 'Kordelio')
    
    # Αντιστοίχηση ονομάτων που στέλνει το frontend
    if location_param == 'Kordelio':
        location = 'Kordelio'
    elif location_param in ['Kordelio-Evosmos', 'Evosmos', 'evosmos']:
        location = 'Kordelio-Evosmos'
    else:
        location = location_param
    
    print(f"🔍 Looking for location: {location_param} -> {location}")
    
    latest = {'date': None, 'no2': 0, 'o3': 0, 'co': 0, 'so2': 0, 'no': 0}
    
    for pollutant in ['no2', 'o3', 'co', 'so2', 'no']:
        try:
            result = supabase.table('air_quality')\
                .select('date', pollutant)\
                .eq('location', location)\
                .gt(pollutant, 0)\
                .order('date', desc=True)\
                .limit(1)\
                .execute()
            
            if result.data and result.data[0].get(pollutant) is not None:
                latest[pollutant] = round(float(result.data[0][pollutant]), 2)
                if latest['date'] is None:
                    latest['date'] = result.data[0]['date']
        except Exception as e:
            print(f"Error for {pollutant}: {e}")
    
    print(f"📤 Returning: {latest}")
    return jsonify({'success': True, 'data': latest})

# ============================================
# 2. MONTHLY DATA (για γραφήματα)
# ============================================
@app.route('/api/monthly', methods=['GET'])
def get_monthly():
    pollutant = request.args.get('pollutant', 'no2')
    year = int(request.args.get('year', 2019))
    location_param = request.args.get('location', 'Kordelio')
    
    if location_param == 'Kordelio':
        location = 'Kordelio'
    else:
        location = 'Kordelio-Evosmos'
    
    allowed = ['no2', 'o3', 'co', 'so2', 'no']
    if pollutant not in allowed:
        return jsonify({'success': False, 'error': 'Invalid pollutant'}), 400
    
    # Παίρνουμε ΟΛΕΣ τις γραμμές (χωρίς gt 0 για να δούμε και τα 0)
    response = supabase.table('air_quality')\
        .select('date', pollutant)\
        .eq('location', location)\
        .eq('year', year)\
        .execute()
    
    month_names = ['Ιαν', 'Φεβ', 'Μαρ', 'Απρ', 'Μαϊ', 'Ιουν', 'Ιουλ', 'Αυγ', 'Σεπ', 'Οκτ', 'Νοε', 'Δεκ']
    
    # Αν δεν υπάρχουν ΚΑΘΟΛΟΥ δεδομένα για τη χρονιά
    if not response.data:
        return jsonify({
            'success': True,
            'months': month_names,
            'values': [0] * 12,
            'hasData': False
        })
    
    # Ομαδοποίηση ανά μήνα (παίρνουμε ΜΕΣΟ ΟΡΟ κάθε μήνα)
    monthly_values = defaultdict(list)
    for row in response.data:
        if row.get(pollutant) is not None:
            month = int(row['date'][5:7]) - 1
            monthly_values[month].append(float(row[pollutant]))
    
    # Υπολογισμός μέσου όρου για κάθε μήνα (αν δεν υπάρχουν δεδομένα, βάζουμε 0)
    averages = []
    for i in range(12):
        if monthly_values[i]:
            avg = sum(monthly_values[i]) / len(monthly_values[i])
            averages.append(round(avg, 1))
        else:
            averages.append(0)
    
    return jsonify({
        'success': True,
        'months': month_names,
        'values': averages,
        'hasData': sum(averages) > 0
    })

# ============================================
# 3. DAILY DATA (για daily aggregation)
# ============================================
@app.route('/api/daily', methods=['GET'])
def get_daily():
    pollutant = request.args.get('pollutant', 'no2')
    year = int(request.args.get('year', 2019))
    location_param = request.args.get('location', 'Kordelio')
    limit = int(request.args.get('limit', 365))
    
    if location_param == 'Kordelio':
        location = 'Kordelio'
    else:
        location = 'Kordelio-Evosmos'
    
    allowed = ['no2', 'o3', 'co', 'so2', 'no']
    if pollutant not in allowed:
        return jsonify({'success': False, 'error': 'Invalid pollutant'}), 400
    
    response = supabase.table('air_quality')\
        .select('date', pollutant)\
        .eq('location', location)\
        .eq('year', year)\
        .gt(pollutant, 0)\
        .order('date', desc=False)\
        .limit(limit)\
        .execute()
    
    if not response.data:
        return jsonify({'success': True, 'dates': [], 'values': []})
    
    dates = [row['date'] for row in response.data]
    values = [round(float(row[pollutant]), 1) for row in response.data]
    
    return jsonify({
        'success': True,
        'dates': dates,
        'values': values
    })

# ============================================
# 4. ALERTS (υπερβάσεις ορίων)
# ============================================
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    alerts = []
    
    limits = [
        ('no2', 100, 'NO₂'),
        ('o3', 100, 'O₃'),
        ('co', 5000, 'CO'),
        ('so2', 150, 'SO₂')
    ]
    
    for pollutant, limit, name in limits:
        try:
            result = supabase.table('air_quality')\
                .select('date, location, ' + pollutant)\
                .gt(pollutant, limit)\
                .order('date', desc=True)\
                .limit(10)\
                .execute()
            
            for row in result.data:
                if row.get(pollutant):
                    alerts.append({
                        'date': row['date'],
                        'location': 'Kordelio' if row['location'] == 'Kordelio' else 'Evosmos',
                        'pollutant': name,
                        'value': round(float(row[pollutant]), 1),
                        'limit': limit
                    })
        except Exception as e:
            print(f"Error for {pollutant}: {e}")
    
    alerts.sort(key=lambda x: x['date'], reverse=True)
    return jsonify({'success': True, 'alerts': alerts[:5]})

# ============================================
# 5. WATER DATA
# ============================================
@app.route('/api/water', methods=['GET'])
def get_water():
    location = request.args.get('location', 'eyosmos')
    
    allowed = ['eyosmos', 'kordelio', 'dialogi']
    if location not in allowed:
        return jsonify({'success': False, 'error': 'Invalid location'}), 400
    
    response = supabase.table('water_quality')\
        .select('*')\
        .eq('location', location)\
        .execute()
    
    if not response.data:
        return jsonify({'success': True, 'data': {}})
    
    water_data = {}
    for row in response.data:
        param = row.get('parameter', '')
        if not param:
            continue
        
        if param not in water_data:
            water_data[param] = []
        
        water_data[param].append({
            'month': row.get('month'),
            'year': row.get('year'),
            'value': row.get('clean_value')
        })
    
    return jsonify({'success': True, 'data': water_data})

# ============================================
# 6. AVAILABLE YEARS (για dropdown)
# ============================================
@app.route('/api/available_years', methods=['GET'])
def get_available_years():
    location_param = request.args.get('location', 'Kordelio')
    
    if location_param == 'Kordelio':
        location = 'Kordelio'
    else:
        location = 'Kordelio-Evosmos'
    
    result = supabase.table('air_quality')\
        .select('year')\
        .eq('location', location)\
        .gt('no2', 0)\
        .execute()
    
    years = sorted(set([row['year'] for row in result.data]))
    
    return jsonify({'success': True, 'years': years})

# ============================================
# 7. HEALTH CHECK
# ============================================
@app.route('/api/health', methods=['GET'])
def health_check():
    try:
        test = supabase.table('air_quality').select('id', count='exact').limit(1).execute()
        return jsonify({'success': True, 'status': 'healthy', 'rows': test.count})
    except Exception as e:
        return jsonify({'success': False, 'status': 'unhealthy', 'error': str(e)}), 500

# ============================================
# 8. EXPORT CSV
# ============================================
@app.route('/api/export', methods=['GET'])
def export_csv():
    pollutant = request.args.get('pollutant', 'no2')
    year = int(request.args.get('year', 2019))
    location_param = request.args.get('location', 'Kordelio')
    
    if location_param == 'Kordelio':
        location = 'Kordelio'
    else:
        location = 'Kordelio-Evosmos'
    
    response = supabase.table('air_quality')\
        .select('date', pollutant)\
        .eq('location', location)\
        .eq('year', year)\
        .gt(pollutant, 0)\
        .order('date', desc=False)\
        .execute()
    
    if not response.data:
        return jsonify({'success': False, 'error': 'No data'}), 404
    
    df = response.data
    output = io.StringIO()
    df.to_csv(output, index=False, encoding='utf-8')
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={pollutant}_{location}_{year}.csv'}
    )

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 BACKEND SERVER - Aer-Aqua (Πλήρης Έκδοση)")
    print("="*60)
    print("\n📌 Endpoints:")
    print("   GET /api/latest?location=Kordelio")
    print("   GET /api/latest?location=Kordelio-Evosmos")
    print("   GET /api/monthly?pollutant=no2&year=2019&location=Kordelio")
    print("   GET /api/daily?pollutant=no2&year=2019&location=Kordelio")
    print("   GET /api/alerts")
    print("   GET /api/water?location=eyosmos")
    print("   GET /api/available_years?location=Kordelio")
    print("   GET /api/export?pollutant=no2&year=2019&location=Kordelio")
    print("   GET /api/health")
    print("\n🌐 http://localhost:5000")
    print("="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=5000)