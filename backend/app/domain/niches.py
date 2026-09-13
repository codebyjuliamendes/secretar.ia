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
    ),
}

DEFAULT_NICHE = "clinica"


def niche_for(key: str | None) -> Niche:
    return NICHES.get(key or DEFAULT_NICHE, NICHES[DEFAULT_NICHE])


def niche_view(key: str | None) -> dict:
    n = niche_for(key)
    return {"key": n.key, "label": n.label, "person": n.person, "people": n.people, "appointment": n.appointment}


def niche_options() -> list[dict]:
    return [{"key": n.key, "label": n.label} for n in NICHES.values()]
