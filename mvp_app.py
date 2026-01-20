from flask import Flask, render_template, request, jsonify, redirect, url_for
from mvp_functions import (
    get_or_create_images,
    generate_question_from_context,
    extract_keywords,
    ask_details,
    save_dream_to_json,
    client)
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
import os, json, random

KST = ZoneInfo("Asia/Seoul")
STATS_FILE = os.path.join("static", "market_stats.json")

app = Flask(__name__)

market_data = {}
last_updated = None

# / → /text_main 자동 이동
@app.route("/")
def index():
    return redirect(url_for('text_main'))   
    
@app.route("/text_main")
def text_main():
    return render_template("text_main.html")

# 질문–답변 페이지로 연결
@app.route("/review")
def review():
    return render_template("review.html")  

# 질문 생성
@app.route("/get_questions", methods=["POST"]) 
def get_questions():
    data = request.get_json(silent=True) or {}
    dream_story = data.get("dream_story", "").strip()
    qa_list = data.get("answers", [])  # 지금까지의 Q&A 히스토리

    if not dream_story:
        return jsonify({"error": "Empty dream story"}), 400

    try:
        question = generate_question_from_context(dream_story, qa_list)

        # 혹시 리스트로 오면 첫 번째만 취함
        if isinstance(question, list) and question:
            question = question[0]

        return jsonify({"question": question}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# 답변 취합 + 요약 + 키워드 + JSON 저장
@app.route("/finalize_dream", methods=["POST"])
def finalize_dream():
    data = request.get_json(silent=True) or {}
    
    dream_story = data.get("dream_story", "")
    qa_list = data.get("qa", [])

    # print("DEBUG finalize_dream payload:", data)
    # print("DEBUG dream_story:", dream_story)
    # print("DEBUG qa_list:", qa_list, type(qa_list))
        
    
    if isinstance(qa_list, dict):
        qa_list = [qa_list]  # 단일 객체일 경우 리스트로 감싸기
    elif not isinstance(qa_list, list):
        qa_list = []
    
    if not dream_story or not qa_list:
        return jsonify({"error": "Missing dream_story or qa"}), 400
    if not qa_list:
         print("⚠️ Warning: qa_list is empty in finalize_dream")

    today = datetime.now()
    today = today.astimezone(KST)    

    # 최종 요약
    final_content = ask_details(dream_story, qa_list)

    # 키워드 추출
    keywords = extract_keywords(final_content)


    dream_details = {
        "name": "User",
        "date": today.strftime("%Y-%m-%d"),
        "time": today.strftime("%H:%M:%S"),
        "dream_story": dream_story,
        "qa": qa_list,
        "final_content": final_content,
        "keywords": keywords,
    }

    save_dream_to_json(dream_details)

    return jsonify(dream_details)#({"message": "Dream saved!", "dream": dream_details})
    
# templates/details.html 파일 열기
@app.route("/details")
def details():
    return render_template("details.html")  

@app.route("/waiting")
def waiting():
    return render_template("waiting.html")

@app.route("/market")
def market():
    return render_template("market.html")

def save_stats(data):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def generate_random_stats():
    demand_options = ["High", "Medium", "Low"]
    usage = f"{random.randint(500, 2000)}+"
    growth = random.choice(
        [f"+{random.randint(1,20)}%", f"-{random.randint(1,10)}%"]
    )
    history = [random.randint(500, 2000) for _ in range(6)]
    return {
        "Demand": random.choice(demand_options),
        "Usage": usage,
        "Growth": growth,
        "History": history
    }

@app.route("/dream_images", methods=["POST"])
def dream_images():
    data = request.get_json(silent=True) or {}
    summary = data.get("summary", "").strip()

    if not summary:
        return jsonify({"error": "Missing summary"}), 400

    try:
        images = get_or_create_images(summary)
        return jsonify({"images": images})
    except Exception as e:
        print("❌ ERROR in /dream_images:", repr(e))
        return jsonify({"error": str(e)}), 500

@app.route("/portfolio")
def portfolio():
    return render_template("portfolio.html")

@app.route("/invest")
def invest():
    return render_template("invest.html")

@app.route("/portfolio_data")
def portfolio_data():
    with open("static/dream_log.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 예시로 Trending/Mover 분리
    trending = data[:2]
    movers = data
    return jsonify({"trending": trending, "movers": movers})

@app.route("/profile")
def profile():
    return redirect(url_for("profile"))

@app.route("/market_data/<keyword>")
def market_data(keyword):
    log_path = os.path.join("static", "dream_log.json")
    img_cache_path = os.path.join("static", "dream_images.json")

    with open(log_path, "r", encoding="utf-8") as f:
        logs = json.load(f)
    with open(img_cache_path, "r", encoding="utf-8") as f:
        images_cache = json.load(f)

    # 키워드 매칭
    for dream in logs:
        if dream["keyword"].lower() == keyword.lower():
            # 이미지 캐시 있으면 추가
            matched_images = []
            for summary, imgs in images_cache.items():
                if summary.strip()[:30] in dream.get("summary", "")[:50]:
                    matched_images = imgs
                    break
            dream["images"] = matched_images
            return jsonify(dream)

    return jsonify({"error": "Keyword not found"}), 404
    
@app.route("/get_image_by_keyword/<keyword>")
def get_image_by_keyword(keyword):
    """dream_log.json에서 키워드로 이미지 찾기"""
    dream_path = os.path.join("static", "dream_log.json")
    if not os.path.exists(dream_path):
        return jsonify({"error": "dream_log.json not found"}), 404

    try:
        with open(dream_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # dream_log.json이 리스트 형태일 수도, dict 안의 리스트일 수도 있음
        dreams = data if isinstance(data, list) else data.get("dreams", [])

        # 키워드 대소문자 무시하고 검색
        match = next(
            (d for d in dreams if d.get("keyword", "").lower() == keyword.lower()), None
        )

        if match and "images" in match:
            # 첫 번째 이미지를 반환 (혹은 랜덤하게 선택)
            image_url = match["images"][0]
            return jsonify({"image": image_url})
        else:
            return jsonify({"error": f"No image found for keyword: {keyword}"}), 404

    except Exception as e:
        print(f"❌ ERROR in get_image_by_keyword: {e}")
        return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001,debug=True)



    
