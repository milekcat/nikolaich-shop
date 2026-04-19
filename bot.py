import requests, time, json

VK_TOKEN = "vk1.a.CgacwOM7IRT16S4_n_lF2lJDd44w_9W5k9LlcEHiXhaonWK7QzPuUyqw0aec3zX6aP1TTcJlos5Mk0lY-YQMNLqhrtXmvRxpZGU6CmSGvUbXAcPK7ZsrQw-_xkl2Zq9g-wG37E_Re6C46yuEMwu99mbKSxWUGSmvG68B2hb_KuCPP1emLhJO_GLE01Pp9amTZbElXOU6g3TGycf8nxh70w"
VK_API_VERSION = "5.131"

AI_URL = "https://api.artemox.com/v1/chat/completions"
AI_API_KEY = "sk-YGn3Z94dTreSNguvMqqa2A"

def get_group_id():
    r = requests.get(f"https://api.vk.com/method/groups.getById?access_token={VK_TOKEN}&v={VK_API_VERSION}").json()
    return r['response'][0]['id']

def send_msg(peer_id, text, keyboard=None):
    data = {"user_id": peer_id, "random_id": 0, "message": text, "access_token": VK_TOKEN, "v": VK_API_VERSION}
    if keyboard:
        data["keyboard"] = json.dumps(keyboard)
    requests.post("https://api.vk.com/method/messages.send", data=data)

def ask_ai(user_msg):
    # Характер нашего бота-продавца
    sys_prompt = "Ты виртуальный помощник фермера Николаича. Общайся с клиентами магазина 'У Николаича' во ВКонтакте. Отвечай дружелюбно, с легким деревенским колоритом, коротко и по делу. Если спрашивают про ассортимент, цены или как заказать - всегда вежливо предлагай перейти на наш сайт nikolaich.shop, чтобы собрать корзину там."
    
    payload = {"model": "gemini-2.5-pro", "temperature": 0.4, "messages": [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_msg}]}
    try:
        r = requests.post(AI_URL, json=payload, headers={"Authorization": f"Bearer {AI_API_KEY}"}, timeout=20)
        return r.json()['choices'][0]['message']['content']
    except:
        return "Ой, что-то интернет в деревне барахлит. Напиши чуть позже, ладно?"

def main():
    print("Запуск ИИ-Бота Николаича...")
    group_id = get_group_id()
    
    # Подключаемся к серверу ВКонтакте
    lp_r = requests.get(f"https://api.vk.com/method/groups.getLongPollServer?group_id={group_id}&access_token={VK_TOKEN}&v={VK_API_VERSION}").json()['response']
    server, key, ts = lp_r['server'], lp_r['key'], lp_r['ts']
    
    # Клавиатура, которая будет показываться клиентам
    kb = {
        "inline": False,
        "buttons": [
            [{"action": {"type": "open_link", "link": "https://nikolaich.shop", "label": "🛒 Открыть витрину магазина"}}],
            [{"action": {"type": "text", "label": "Позвать Николаича"}, "color": "secondary"}]
        ]
    }

    print("Бот успешно запущен и слушает сообщения группы!")
    while True:
        try:
            r = requests.get(f"{server}?act=a_check&key={key}&ts={ts}&wait=25", timeout=35).json()
            if 'failed' in r:
                lp_r = requests.get(f"https://api.vk.com/method/groups.getLongPollServer?group_id={group_id}&access_token={VK_TOKEN}&v={VK_API_VERSION}").json()['response']
                server, key, ts = lp_r['server'], lp_r['key'], lp_r['ts']
                continue
            
            ts = r['ts']
            for update in r.get('updates', []):
                if update['type'] == 'message_new':
                    msg = update['object']['message']
                    text = msg.get('text', '')
                    peer_id = msg['from_id']
                    
                    # Проверяем, не сам ли Николаич отвечает из админки
                    if peer_id > 0: 
                        if text == "Позвать Николаича":
                            send_msg(peer_id, "🚜 Передал твой запрос Николаичу! Сейчас он додоит корову, прочитает и ответит тебе лично.", kb)
                        elif text:
                            # Отправляем сообщение ИИ и возвращаем ответ
                            reply = ask_ai(text)
                            send_msg(peer_id, reply, kb)
        except Exception as e:
            time.sleep(2)

if __name__ == '__main__':
    main()
