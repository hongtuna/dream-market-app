import os
import json
from datetime import datetime
from openai import OpenAI
from pytz import timezone
from datetime import datetime
from zoneinfo import ZoneInfo
import httpx
import re
import random


client = OpenAI(
    api_key='your-api-key-here',
    http_client=httpx.Client(verify=False) 
)


KST = ZoneInfo("Asia/Seoul")

# GPT 호출 함수
def ask_gpt_api(question, message_history = None, model="gpt-4o"):
    if message_history is None:
        message_history = [
            { "role":"system",
              "content": "You are a helpful assistant. You must answer in English."
            }]
    
    message_history.append({"role": "user", "content": question})
    gpt_response = client.chat.completions.create(
        model=model,
        messages=message_history,
        max_tokens=100)
    
    answer = gpt_response.choices[0].message.content.strip()
    message_history.append({"role": "assistant", "content": answer})
    return answer, message_history


# 추가 질문 생성 함수
def generate_question_from_context(dream_story, qa_list=None):
    if qa_list is None:
        qa_list = []

    context = f"Dream Story: {dream_story}\n\n"
    for i, qa in enumerate(qa_list, 1):
        context += f"Q{i}: {qa['question']}\nA{i}: {qa['answer']}\n\n"

    prompt = f"""
    You are helping a user describe a dream more completely.
    Current context:
    {context}

    Task:
    - Generate exactly 1 follow-up question.
    - Question must be in simple English.
    - Follow 5W1H (Who, What, When, Where, Why, How).
    - Focus on missing or unclear details in the context.
    - Return only the question sentence.
    """

    question, _ = ask_gpt_api(prompt)
    return question.strip()


# 키워드 추출 함수
def extract_keywords(content, message_history=None):
    prompt = f"Extract keywords from the following dream content: {content}\nProvide a list of 3-5 keywords."
    # answer, message_history = ask_gpt_api(prompt, message_history)
    # keywords = [kw.strip() for kw in answer.split(",") if kw.strip()]
    # return keywords, message_history
    answer, _ = ask_gpt_api(prompt, message_history)
    raw_keywords = answer.replace("\n", ",").split(",")

    # 앞에 붙은 번호/불필요한 점 제거
    keywords = [re.sub(r'^\d+[\.\)]\s*', '', kw).strip() for kw in raw_keywords if kw.strip()]
    return keywords


def ask_details(dream_story, qa_list, message_history=None):
    context = f"Dream Story: {dream_story}\n\n"
    for i, qa in enumerate(qa_list, 1):
        context += f"Q{i}: {qa['question']}\nA{i}: {qa['answer']}\n\n"

    final_content, message_history = ask_gpt_api(
        f"""
        You are given a dream story and follow-up Q&A:
        {context}

        Task:
        - Write one coherent paragraph combining the story and all answers.
        - Use only the information provided by the user.
        - Do not invent details.
        - Keep it natural and narrative.
        """,
        message_history
    )
    return final_content


IMAGE_CACHE_FILE = os.path.join("static", "dream_images.json")
def get_or_create_images(summary):
    """dream_images.json에 저장된 이미지 캐시를 불러오거나 새로 생성"""
    os.makedirs(os.path.dirname(IMAGE_CACHE_FILE), exist_ok=True)

    # 파일이 없으면 생성
    if not os.path.exists(IMAGE_CACHE_FILE):
        with open(IMAGE_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=4)

    # 기존 캐시 읽기
    with open(IMAGE_CACHE_FILE, "r", encoding="utf-8") as f:
        try:
            cache = json.load(f)
        except json.JSONDecodeError:
            cache = {}

    # 1️⃣ 이미 캐시된 summary면 그대로 반환
    if summary in cache:
        print(f"[CACHE HIT] Returning cached images for: {summary[:40]}...")
        return cache[summary]

    # 2️⃣ 없으면 새 이미지 생성
    print(f"[CACHE MISS] Generating new images for: {summary[:40]}...")
    prompt = f"A surreal, dreamlike artistic illustration inspired by the dream: {summary}"
    result = client.images.generate(
        model="dall-e-2",  # "gpt-image-1"도 가능
        prompt=prompt,
        size="512x512",    # 품질 조정 가능
        n=4
    )

    image_urls = [img.url for img in result.data]

    # 3️⃣ 캐시에 저장
    cache[summary] = image_urls
    with open(IMAGE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=4)

    return image_urls

def save_dream_to_json(dream_details):
    """새로운 꿈 데이터를 static/dream_log.json에 통합 저장"""
    log_path = os.path.join("static", "dream_log.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)

    # 기존 파일 불러오기 (없으면 빈 리스트)
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []

    # keywords 중 첫 번째 키워드로 대표 keyword 설정
    keyword = dream_details.get("keywords", ["Dream"])[0] if dream_details.get("keywords") else "Dream"

    # 랜덤 stats 생성
    stats = {
        "Demand": random.choice(["High", "Medium", "Low"]),
        "Usage": f"{random.randint(500, 2000)}+",
        "Growth": random.choice([f"+{random.randint(1,20)}%", f"-{random.randint(1,10)}%"]),
        "History": [random.randint(500, 2000) for _ in range(6)]
    }

    new_entry = {
        "keyword": keyword,
        "summary": dream_details.get("final_content", ""),
        "images": [],  # 나중에 /dream_images로 채움
        "stats": stats
    }
    
    images = get_or_create_images(dream_details["final_content"])
    new_entry["images"] = images
    
    logs.append(new_entry)

    # 저장
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)

    print(f"✅ Added new dream to {log_path}: {keyword}")
