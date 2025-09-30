import os
import requests
from flask import Flask, jsonify, request

# .env फ़ाइल से environment variables को लोड करने के लिए, 
# production में इसकी ज़रूरत नहीं होगी, लेकिन लोकल डेवलपमेंट के लिए अच्छा है।
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

# API बेस URL को environment variable से लेना सुरक्षित होता है।
# अगर .env में नहीं मिला, तो default value का उपयोग करें।
API_BASE_URL = os.getenv("API_BASE_URL", "https://freeapi.frappeash.workers.dev/")

@app.route('/api/details', methods=['GET'])
def get_user_details():
    """
    यूजर से 'num' पैरामीटर लेता है और API को कॉल करके 
    व्यक्तिगत विवरण वापस करता है।
    """
    # 1. 'num' पैरामीटर प्राप्त करें।
    num = request.args.get('num')
    
    if not num:
        return jsonify({"error": "Number (num) parameter is missing."}), 400

    # 2. API URL बनाएं (नंबर को curly braces में संलग्न करें, जैसा कि ज़रूरी है)।
    # उदाहरण: https://freeapi.frappeash.workers.dev/?num={9798423774}
    api_url = f"{API_BASE_URL}?num={{{num}}}"

    try:
        # 3. API को कॉल करें।
        response = requests.get(api_url, timeout=10)
        response.raise_for_status() # HTTP errors (4xx, 5xx) के लिए एक exception उठाएँ।

        # 4. JSON जवाब को Parse करें।
        data = response.json()

        # 5. केवल 'result' array के पहले एलिमेंट से डेटा निकालें।
        if 'result' in data and isinstance(data['result'], list) and len(data['result']) > 0:
            user_data = data['result'][0]
            
            # **ज़रूरी:** यहाँ से 'Api_owner' जैसी अनावश्यक keys को हटा दें।
            if 'Api_owner' in user_data:
                del user_data['Api_owner']
                
            # साफ़ किया हुआ (cleaned) डेटा भेजें।
            return jsonify(user_data)
        
        else:
            # अगर 'result' array खाली है या सही format में नहीं है।
            return jsonify({"message": "No data found for this number.", "data": data.get('result')}), 404

    except requests.exceptions.RequestException as e:
        # API कॉल से संबंधित errors (जैसे कनेक्शन फ़ेलियर, timeout) को संभालें।
        print(f"API Request Error: {e}")
        return jsonify({"error": "Failed to connect to external API.", "details": str(e)}), 503
        
    except Exception as e:
        # अन्य सभी errors को संभालें।
        print(f"An unexpected error occurred: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

if __name__ == '__main__':
    # लोकल मशीन पर चलाने के लिए
    app.run(debug=True, port=os.getenv("PORT", 5000))
