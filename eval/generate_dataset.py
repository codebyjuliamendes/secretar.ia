import json
import random

intents = {
    "AGENDAR": [
        "Quero marcar botox", "Gostaria de agendar uma consulta", "Tem horário sexta?",
        "Preciso de uma avaliação", "Quero agendar preenchimento", "Como marco uma sessão?",
        "Pode me arrumar um horário amanhã?", "Quero fazer harmonização, como agendo?",
        "Teria vaga pra Dra Ana amanhã?", "Oi, gostaria de marcar meu retorno."
    ],
    "CANCELAR": [
        "Preciso desmarcar amanhã", "Não vou conseguir ir hoje", "Cancela minha consulta",
        "Tive um imprevisto, pode cancelar?", "Quero cancelar meu horário",
        "Infelizmente vou ter que cancelar", "Pode tirar meu nome da agenda de amanhã",
        "Vou precisar desmarcar", "Cancela por favor", "Não poderei comparecer."
    ],
    "REMARCAR": [
        "Queria mudar meu horário", "Podemos passar pra semana que vem?", "Preciso remarcar",
        "Como faço pra trocar o dia?", "Quero remarcar a consulta de hoje", 
        "Dá pra transferir pra quinta?", "Queria adiar meu procedimento", 
        "Teria como mudar meu agendamento?", "Pode reagendar?", "Gostaria de mudar a data."
    ],
    "INFO": [
        "Qual o valor do botox?", "Onde vocês ficam?", "Quais os horários de atendimento?",
        "Vocês aceitam cartão?", "Qual o preço do preenchimento labial?",
        "Como funciona o peeling?", "Onde é o endereço?", "Até que horas fica aberto?",
        "Qual a política de cancelamento?", "Vocês parcelam?"
    ],
    "HUMANO": [
        "Estou com dor após o procedimento", "Quero falar com a gerente",
        "O botox ficou torto", "Meu rosto está inchado", "Quero reclamar do atendimento",
        "Tem alguém aí?", "Quero falar com uma pessoa", "Preciso falar com a Dra urgente",
        "Estou passando mal", "Alguém pode me ligar?"
    ]
}

def generate_dataset():
    dataset = []
    # Generate exactly 100 lines
    for _ in range(100):
        intent = random.choice(list(intents.keys()))
        phrase = random.choice(intents[intent])
        # Add some noise to make it realistic
        noise = random.choice(["", " oi,", " bom dia,", " ", " pfv ", " moça "])
        phrase = noise + phrase + random.choice(["", ".", "!", "?", " rs", "🙏"])
        phrase = phrase.strip().capitalize()
        dataset.append({
            "message": phrase,
            "expected_intent": intent
        })
    
    with open('dataset-recepcio.jsonl', 'w', encoding='utf-8') as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')

if __name__ == "__main__":
    generate_dataset()
    print("Dataset generated successfully.")
