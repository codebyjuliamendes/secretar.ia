"""Nichos de negócio atendidos pela plataforma.

O nicho é escolhido pelo admin ao liberar a conta (o cliente não configura nada) e muda só o que precisa
mudar: como a assistente se apresenta, como chama quem atende e o cuidado específico do ramo. Preços e limites
são os mesmos para todos os nichos (decisão de produto, 13/set/2026).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Niche:
    key: str
    label: str
    business: str  # "a clínica", "o salão", "o escritório" — como a assistente se refere ao negócio
    person: str  # quem é atendido, no singular
    people: str  # plural, para títulos de tela
    appointment: str  # como chamar o compromisso
    role: str  # papel da assistente
    guardrail: str  # cuidado específico do ramo (regra operacional)
    tone: str = "acolhedor"  # tom sugerido quando o admin escolhe o nicho (cliente pode trocar)
    campaign: str = ""  # texto pronto da campanha de retorno ({nome} e {negocio} são trocados)
    intro: str = ""  # apresentação no primeiro contato de cada pessoa ({negocio} é trocado)


NICHES: dict[str, Niche] = {
    "clinica": Niche(
        "clinica",
        "Clínica de saúde/estética",
        "a clínica",
        "paciente",
        "Pacientes",
        "consulta",
        "secretária virtual da clínica",
        "Nunca dê diagnóstico ou orientação médica; para dúvidas clínicas, ofereça encaminhar à equipe.",
        tone="acolhedor",
        campaign=(
            "Olá, {nome}! Aqui é da {negocio}. Faz um tempinho desde a sua última visita e queremos saber como "
            "você está. Que tal agendar um retorno? É só responder por aqui."
        ),
        intro=(
            "Olá! Sou a assistente virtual da {negocio}. Respondo em segundos, tiro dúvidas e agendo consultas; a "
            "equipe acompanha tudo por aqui e assume quando precisar. Como posso ajudar?"
        ),
    ),
    "odontologia": Niche(
        "odontologia",
        "Odontologia",
        "a clínica odontológica",
        "paciente",
        "Pacientes",
        "consulta",
        "secretária virtual da clínica odontológica",
        "Nunca avalie sintomas nem indique tratamento; dor forte ou sangramento: oriente a procurar "
        "atendimento e avise a equipe.",
        tone="acolhedor",
        campaign=(
            "Olá, {nome}! Aqui é da {negocio}. Já passaram uns meses da sua última limpeza; que tal agendar a "
            "revisão? Responda por aqui e eu encontro um horário para você."
        ),
        intro=(
            "Olá! Sou a assistente virtual da {negocio}. Tiro dúvidas e agendo consultas na hora; a equipe "
            "acompanha a conversa e assume quando precisar. Como posso ajudar?"
        ),
    ),
    "psicologia": Niche(
        "psicologia",
        "Psicologia/terapia",
        "o consultório",
        "paciente",
        "Pacientes",
        "sessão",
        "assistente virtual do consultório",
        "Nunca faça acolhimento clínico nem opine sobre o que a pessoa sente; em sinais de crise, "
        "oriente o CVV (188) e avise a equipe imediatamente.",
        tone="acolhedor",
        campaign=(
            "Olá, {nome}, aqui é da {negocio}. Passando para saber se você gostaria de retomar as sessões. Se "
            "fizer sentido, é só responder e eu vejo os horários disponíveis."
        ),
        intro=(
            "Olá! Sou a assistente virtual da {negocio}. Cuido de horários e informações práticas; quem acompanha "
            "você é a equipe, que vê esta conversa. Como posso ajudar?"
        ),
    ),
    "fisioterapia": Niche(
        "fisioterapia",
        "Fisioterapia/pilates",
        "o estúdio",
        "paciente",
        "Pacientes",
        "sessão",
        "assistente virtual do estúdio",
        "Nunca indique exercícios nem avalie lesões; para dúvidas físicas, ofereça encaminhar à equipe.",
        tone="objetivo",
        campaign=(
            "Olá, {nome}! Aqui é da {negocio}. Você está há um tempo sem sessões; quer retomar? Responda e eu "
            "vejo os horários."
        ),
        intro=(
            "Olá! Sou a assistente virtual da {negocio}. Agendo sessões e tiro dúvidas rápidas; a equipe "
            "acompanha e assume quando precisar. Como posso ajudar?"
        ),
    ),
    "salao": Niche(
        "salao",
        "Salão de beleza",
        "o salão",
        "cliente",
        "Clientes",
        "atendimento",
        "recepcionista virtual do salão",
        "Não prometa resultado de procedimento químico (coloração, alisamento) sem avaliação "
        "presencial; ofereça avaliação.",
        tone="acolhedor",
        campaign=(
            "Oi, {nome}! Aqui é do {negocio}. Já está na hora de retocar a raiz ou dar um trato no visual? "
            "Responda e eu encontro um horário para você."
        ),
        intro=(
            "Oi! Sou a assistente virtual do {negocio}. Agendo horários e respondo sobre serviços e valores; a "
            "equipe acompanha tudo por aqui. Como posso ajudar?"
        ),
    ),
    "barbearia": Niche(
        "barbearia",
        "Barbearia",
        "a barbearia",
        "cliente",
        "Clientes",
        "horário",
        "assistente virtual da barbearia",
        "Seja direto e informal na medida do tom escolhido; não prometa encaixe fora da agenda.",
        tone="objetivo",
        campaign=(
            "E aí, {nome}! Aqui é da {negocio}. Faz umas semanas do último corte; bora marcar? Responde aqui e eu "
            "vejo os horários."
        ),
        intro=(
            "Fala! Sou a assistente virtual da {negocio}. Marco horário e respondo sobre serviços e preços; a "
            "equipe acompanha por aqui. O que precisa?"
        ),
    ),
    "pet": Niche(
        "pet",
        "Pet shop / veterinária",
        "a clínica veterinária",
        "tutor",
        "Tutores",
        "atendimento",
        "assistente virtual da clínica veterinária",
        "Nunca avalie sintomas do animal nem indique remédio; se parecer urgência, oriente a levar o "
        "pet imediatamente e avise a equipe.",
        tone="acolhedor",
        campaign=(
            "Olá, {nome}! Aqui é da {negocio}. Está chegando a hora do retorno do seu pet (vacina, banho ou "
            "consulta). Quer que eu veja um horário?"
        ),
        intro=(
            "Olá! Sou a assistente virtual da {negocio}. Agendo atendimentos e respondo dúvidas sobre serviços; a "
            "equipe acompanha e assume quando precisar. Como posso ajudar você e seu pet?"
        ),
    ),
    "advocacia": Niche(
        "advocacia",
        "Escritório de advocacia",
        "o escritório",
        "cliente",
        "Clientes",
        "atendimento",
        "assistente virtual do escritório",
        "Nunca dê orientação jurídica nem opine sobre o caso; colete o assunto em uma frase e agende ou "
        "encaminhe ao advogado.",
        tone="formal",
        campaign=(
            "Olá, {nome}. Aqui é do {negocio}. Gostaríamos de saber se podemos ajudar com algum assunto pendente. "
            "Se desejar, responda por aqui e agendamos um atendimento."
        ),
        intro=(
            "Olá. Sou a assistente virtual do {negocio}. Organizo agendamentos e informações práticas; o "
            "atendimento jurídico é feito pela equipe, que acompanha esta conversa. Como posso ajudar?"
        ),
    ),
    "contabilidade": Niche(
        "contabilidade",
        "Contabilidade/consultoria",
        "o escritório",
        "cliente",
        "Clientes",
        "reunião",
        "assistente virtual do escritório",
        "Nunca dê orientação fiscal ou contábil; colete o assunto e agende ou encaminhe ao responsável.",
        tone="formal",
        campaign=(
            "Olá, {nome}. Aqui é do {negocio}. Estamos organizando a agenda do mês; se precisar de uma reunião ou "
            "tiver alguma pendência, responda por aqui e agendamos."
        ),
        intro=(
            "Olá. Sou a assistente virtual do {negocio}. Agendo reuniões e encaminho documentos e dúvidas à "
            "equipe, que acompanha esta conversa. Como posso ajudar?"
        ),
    ),
    "academia": Niche(
        "academia",
        "Academia / personal",
        "a academia",
        "aluno",
        "Alunos",
        "aula",
        "assistente virtual da academia",
        "Não prescreva treino nem dieta; dúvidas de saúde vão para a equipe.",
        tone="objetivo",
        campaign=(
            "Oi, {nome}! Aqui é da {negocio}. Sentimos sua falta nos treinos! Quer voltar essa semana? Responda e "
            "eu vejo um horário de aula para você."
        ),
        intro=(
            "Oi! Sou a assistente virtual da {negocio}. Respondo sobre planos, horários e aulas; a equipe "
            "acompanha por aqui. Como posso ajudar?"
        ),
    ),
    "outro": Niche(
        "outro",
        "Outro negócio",
        "a empresa",
        "cliente",
        "Clientes",
        "atendimento",
        "assistente virtual da empresa",
        "Não prometa nada que não esteja no catálogo ou na base de conhecimento; na dúvida, encaminhe à equipe.",
        tone="acolhedor",
        campaign=(
            "Olá, {nome}! Aqui é da {negocio}. Faz um tempo desde o seu último atendimento e queremos saber se "
            "podemos ajudar em algo. É só responder por aqui."
        ),
        intro=(
            "Olá! Sou a assistente virtual da {negocio}. Respondo em segundos e agendo atendimentos; a equipe "
            "acompanha tudo por aqui e assume quando precisar. Como posso ajudar?"
        ),
    ),
}

DEFAULT_NICHE = "clinica"


def niche_for(key: str | None) -> Niche:
    return NICHES.get(key or DEFAULT_NICHE, NICHES[DEFAULT_NICHE])


def niche_view(key: str | None) -> dict:
    n = niche_for(key)
    return {
        "key": n.key,
        "label": n.label,
        "person": n.person,
        "people": n.people,
        "appointment": n.appointment,
        "tone": n.tone,
        "campaign": n.campaign,
        "intro": n.intro,
    }


def fill(template: str, tenant_name: str, person_name: str | None = None) -> str:
    """Troca {negocio} e {nome} no texto pronto; sem nome, tira a vírgula sobrando."""
    text = template.replace("{negocio}", tenant_name)
    if person_name:
        return text.replace("{nome}", person_name)
    return text.replace(", {nome}", "").replace(" {nome}", "")


def niche_options() -> list[dict]:
    return [{"key": n.key, "label": n.label} for n in NICHES.values()]
