# stock-sense-ai

## Features

- Sentiment analysis of stocks based on news articles using OpenAI's GPT model.
- Retrieves stock-related news articles via the Polygon API and provides actionable insights.
- Provides recommendations (e.g., Buy, Strong Buy, Do Not Buy) based on sentiment analysis.
- Integration with OpenAI for advanced sentiment analysis and stock recommendations.

---

## Prerequisites

- Python 3.7 or higher  
- Flask  
- OpenAI Python client  
- Polygon API key  
- Python Dotenv  

---

## Setup Instructions

### 1. Clone the repository:
```bash
git clone https://github.com/your_username/stock-sense-ai.git
cd stock-sense-ai
```

### 2. Install the required packages:

```bash
pip install flask openai python-dotenv requests
```

### 3. Set up environment variables:
Create a `.env` file at the project root and add your OpenAI API key and Polygon API key:

```bash
polygon_api_key=your_polygon_api_key_here
openai_api_key=your_openai_api_key_here
```

## Usage

### 1. Running the Application:

Run the app locally:

```bash
python3 app.py
```

## APIs

### 1️⃣ Home Page

#### Description:
Returns a welcome message with the current timestamp.

#### Endpoint:

```bash
GET http://127.0.0.1:8888/
```

#### Sample cURL:

```bash
curl -X GET http://127.0.0.1:8888/
```

#### Sample Response:

```bash
{
    "Page": "Home",
    "Message": "Welcome to Stock App Page",
    "TimeStamp": 1698725464.123456
}
```

### 2️⃣ Stock Sentiment Analysis

#### Description:
Fetches stock-related news articles from Polygon API and uses OpenAI’s GPT to analyze and provide sentiment recommendations.

#### Endpoint:
```bash
GET http://127.0.0.1:8888/sentiment/?ticker={ticker}&limit={limit}
```
#### Query Parameters:

`ticker`: The stock ticker symbol (e.g., "AAPL" for Apple).
`limit`: Number of news articles to retrieve (default is 10).

#### Sample cURL:
```bash
curl -X GET "http://127.0.0.1:8888/sentiment/?ticker=AAPL&limit=5"
```
#### Sample Response:
```bash
{
"sentiments": [
{
"reason": "Stock fell 18.1% due to trade war tensions with China, potential tariff impacts, and disappointing AI technology progress, including delayed Siri AI features and potential reliance on third-party AI models",
"recommendation": "Do Not Buy",
"sentiment_score": 40,
"source": "https://www.fool.com/investing/2025/07/14/why-apple-fell-181-in-the-first-half-of-2025/?source=iedfolrf0000001",
"stock_name": "Apple Inc.",
"ticker": "AAPL"
},
{
"reason": "Strong AI potential through AWS cloud services and robotics integration, seen as having significant long-term growth opportunities",
"recommendation": "Buy",
"sentiment_score": 80,
"source": "https://www.fool.com/investing/2025/07/14/warren-buffett-has-658-billion-invested-in-these-4/?source=iedfolrf0000001",
"stock_name": "Amazon.com Inc.",
"ticker": "AMZN"
},
{
"reason": "Stock price showed modest gain (+0.83%), suggesting mild investor optimism",
"recommendation": "Do Not Buy",
"sentiment_score": 60,
"source": "https://m.investing.com/analysis/sp-500-key-weekly-levels-and-price-targets-200663654?ampMode=1",
"stock_name": "Tesla Inc.",
"ticker": "TSLA"
},
{
"reason": "Stock price remained nearly unchanged (-0.02%), indicating stable market perception",
"recommendation": "Do Not Buy",
"sentiment_score": 50,
"source": "https://m.investing.com/analysis/sp-500-key-weekly-levels-and-price-targets-200663654?ampMode=1",
"stock_name": "NVIDIA Corporation",
"ticker": "NVDA"
},
{
"reason": "Small portfolio position with limited AI growth prospects compared to other tech companies",
"recommendation": "Do Not Buy",
"sentiment_score": 50,
"source": "https://www.fool.com/investing/2025/07/14/warren-buffett-has-658-billion-invested-in-these-4/?source=iedfolrf0000001",
"stock_name": "Cisco Systems Inc.",
"ticker": "CSCO"
},
{
"reason": "Small portfolio position with specialized business and potentially constrained AI growth opportunities",
"recommendation": "Do Not Buy",
"sentiment_score": 50,
"source": "https://www.fool.com/investing/2025/07/14/warren-buffett-has-658-billion-invested-in-these-4/?source=iedfolrf0000001",
"stock_name": "Qualcomm Inc.",
"ticker": "QCOM"
},
{
"reason": "Solid foundation in networking solutions and wireless chips, not primarily chosen for AI",
"recommendation": "Do Not Buy",
"sentiment_score": 50,
"source": "https://www.fool.com/investing/2025/07/14/billionaire-warren-buffett-owns-5-ai-stocks-catch/?source=iedfolrf0000001",
"stock_name": "Broadcom Inc.",
"ticker": "AVGO"
},
{
"reason": "Strong cloud platform Azure, robust legacy operations, and AI integration potential",
"recommendation": "Buy",
"sentiment_score": 80,
"source": "https://www.fool.com/investing/2025/07/14/billionaire-warren-buffett-owns-5-ai-stocks-catch/?source=iedfolrf0000001",
"stock_name": "Microsoft Corporation",
"ticker": "MSFT"
},
{
"reason": "Dominant search engine market share, YouTube platform, and emerging AI capabilities",
"recommendation": "Buy",
"sentiment_score": 80,
"source": "https://www.fool.com/investing/2025/07/14/billionaire-warren-buffett-owns-5-ai-stocks-catch/?source=iedfolrf0000001",
"stock_name": "Alphabet Inc.",
"ticker": "GOOG"
},
{
"reason": "Dominant search engine market share, YouTube platform, and emerging AI capabilities",
"recommendation": "Buy",
"sentiment_score": 80,
"source": "https://www.fool.com/investing/2025/07/14/billionaire-warren-buffett-owns-5-ai-stocks-catch/?source=iedfolrf0000001",
"stock_name": "Alphabet Inc.",
"ticker": "GOOGL"
}
]
}
```













