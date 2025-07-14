from flask import Flask, jsonify, request
from newspaper import Article

app = Flask(__name__)


@app.route('/scrapper/', methods=['GET'])
def scrape_webpage():
    # Get the URL from the query parameters
    url = "https://www.fool.com/investing/2024/08/02/why-nvidia-stock-kept-tumbling-on-friday/?source=iedfolrf0000001"
    
    
    # url = request.args.get('https://www.fool.com/investing/2024/08/02/why-nvidia-stock-kept-tumbling-on-friday/?source=iedfolrf0000001', None)
    
    if not url:
        return jsonify({"error": "URL parameter is required"}), 400

    try:
        # Use newspaper3k to download and parse the article
        article = Article(url)
        article.download()
        article.parse()
        
        if not article.text:
            raise Exception("Failed to extract article content")
        
        # Return the extracted text as a JSON response
        return jsonify({"article_text": article.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)