/**
 * Conteúdo das páginas públicas por ramo (/para/[nicho]). As chaves espelham backend/app/domain/niches.py;
 * o texto é de marketing e vive só aqui. Preços vêm do backend (mesmos para todos os ramos).
 */

export interface NichePage {
  key: string;
  slug: string;
  label: string; // como aparece no menu
  eyebrow: string; // "Para salões de beleza"
  headline: string;
  sub: string;
  people: string; // plural em minúsculas, para a tabela de planos
  person: string;
  features: { title: string; text: string }[];
  chat: { from: "cliente" | "assistente"; text: string }[];
  care: string; // o cuidado do ramo, em uma frase
}

export const NICHE_PAGES: NichePage[] = [
  {
    key: "clinica",
    slug: "clinicas",
    label: "Clínicas",
    eyebrow: "Para clínicas de saúde e estética",
    headline: "Sua secretária virtual no WhatsApp, com agenda, pacientes e retorno.",
    sub: "Responde dúvidas, informa valores e horários, agenda só nos horários livres e chama a equipe quando o paciente pede uma pessoa.",
    people: "pacientes",
    person: "paciente",
    features: [
      { title: "Agenda sem furo", text: "Oferece apenas horários livres e registra o pedido como pendente para a equipe confirmar." },
      { title: "Retorno no prazo certo", text: "Cinco meses depois do procedimento, o paciente recebe o convite de retorno automaticamente." },
      { title: "Nunca dá diagnóstico", text: "Dúvidas clínicas vão para a equipe. A assistente informa, agenda e encaminha." },
    ],
    chat: [
      { from: "cliente", text: "Oi, quanto custa a limpeza de pele?" },
      { from: "assistente", text: "Olá! A limpeza de pele custa R$ 180 e dura 50 min. Tenho quinta às 14h ou sexta às 10h. Quer reservar?" },
      { from: "cliente", text: "Sexta às 10h" },
      { from: "assistente", text: "Reservado para sexta, 10h, com a Dra. Ana. A clínica confirma por aqui. Precisa de mais alguma coisa?" },
    ],
    care: "Nunca dá diagnóstico nem orientação médica; encaminha à equipe.",
  },
  {
    key: "odontologia",
    slug: "odontologia",
    label: "Odontologia",
    eyebrow: "Para consultórios odontológicos",
    headline: "Atendimento no WhatsApp que marca a consulta e lembra da revisão.",
    sub: "Tira dúvidas sobre procedimentos e valores, agenda nos horários livres e convida para a limpeza semestral sem ninguém precisar lembrar.",
    people: "pacientes",
    person: "paciente",
    features: [
      { title: "Urgência bem encaminhada", text: "Dor forte ou sangramento: orienta a procurar atendimento e avisa a equipe na hora." },
      { title: "Revisão a cada 6 meses", text: "O convite de retorno sai sozinho no prazo certo, uma vez por atendimento." },
      { title: "Convênios e valores claros", text: "Cole a lista de convênios na base de conhecimento e a assistente responde certo." },
    ],
    chat: [
      { from: "cliente", text: "Vocês atendem Unimed?" },
      { from: "assistente", text: "Olá! Sim, atendemos Unimed e Bradesco Saúde. Quer agendar uma avaliação? Tenho terça às 9h e quarta às 15h30." },
      { from: "cliente", text: "Terça 9h por favor" },
      { from: "assistente", text: "Agendado: terça, 9h, avaliação. Traga a carteirinha e um documento. Até lá!" },
    ],
    care: "Nunca avalia sintomas nem indica tratamento.",
  },
  {
    key: "psicologia",
    slug: "psicologia",
    label: "Psicologia",
    eyebrow: "Para psicólogos e terapeutas",
    headline: "Uma assistente discreta para agenda e informações práticas.",
    sub: "Cuida de horários, valores e remarcações com sigilo. O acolhimento é sempre seu: ela nunca opina sobre o que a pessoa sente.",
    people: "pacientes",
    person: "paciente",
    features: [
      { title: "Só o prático", text: "Horários, valores, forma de pagamento e remarcação. Nada de conversa clínica." },
      { title: "Sinais de crise", text: "Orienta o CVV (188) e avisa você imediatamente." },
      { title: "Retomada de sessões", text: "Quem parou há um mês recebe um convite gentil para voltar, se você quiser." },
    ],
    chat: [
      { from: "cliente", text: "Preciso remarcar a sessão de quinta" },
      { from: "assistente", text: "Claro. Tenho quinta às 18h ou sexta às 8h. Qual prefere?" },
      { from: "cliente", text: "Sexta 8h" },
      { from: "assistente", text: "Remarcado para sexta, 8h. A psicóloga confirma por aqui. Cuide-se!" },
    ],
    care: "Não faz acolhimento clínico; em crise, orienta o CVV e avisa a equipe.",
  },
  {
    key: "fisioterapia",
    slug: "fisioterapia",
    label: "Fisioterapia",
    eyebrow: "Para fisioterapia e pilates",
    headline: "Sessões marcadas pelo WhatsApp, sem parar o atendimento.",
    sub: "A assistente agenda e remarca sessões, informa pacotes e horários e chama você quando a dúvida é física.",
    people: "pacientes",
    person: "paciente",
    features: [
      { title: "Pacotes e sessões", text: "Informa valores de sessão avulsa e pacotes e agenda nos horários livres." },
      { title: "Sem prescrição", text: "Dúvidas sobre exercícios e lesões vão para a equipe." },
      { title: "Volta quem parou", text: "Trinta dias sem sessão? Um convite de retorno sai sozinho." },
    ],
    chat: [
      { from: "cliente", text: "Quanto é o pacote de 10 sessões de pilates?" },
      { from: "assistente", text: "Olá! O pacote de 10 sessões sai por R$ 750. Tenho vaga segunda e quarta às 7h. Quer começar essa semana?" },
      { from: "cliente", text: "Segunda 7h" },
      { from: "assistente", text: "Reservado: segunda, 7h. Venha com roupa confortável. Até lá!" },
    ],
    care: "Não indica exercícios nem avalia lesões.",
  },
  {
    key: "salao",
    slug: "saloes",
    label: "Salões",
    eyebrow: "Para salões de beleza",
    headline: "Agenda cheia sem parar o secador para responder.",
    sub: "A recepcionista virtual informa serviços e valores, marca horários e lembra a cliente de retocar a raiz na hora certa.",
    people: "clientes",
    person: "cliente",
    features: [
      { title: "Responde em segundos", text: "Enquanto você atende, ela marca. Só oferece horários realmente livres." },
      { title: "Retoque no prazo", text: "Cinco semanas depois, a cliente recebe o convite para retocar a raiz." },
      { title: "Sem promessa de química", text: "Coloração e alisamento passam por avaliação presencial. Ela oferece a avaliação." },
    ],
    chat: [
      { from: "cliente", text: "Oi! Quanto tá a escova e tem horário sábado?" },
      { from: "assistente", text: "Oi! A escova está R$ 60. Sábado tenho 9h, 11h30 e 15h. Qual fica bom?" },
      { from: "cliente", text: "11h30" },
      { from: "assistente", text: "Marcado: sábado, 11h30, escova. Te esperamos!" },
    ],
    care: "Não promete resultado de procedimento químico sem avaliação presencial.",
  },
  {
    key: "barbearia",
    slug: "barbearias",
    label: "Barbearias",
    eyebrow: "Para barbearias",
    headline: "Corte marcado pelo WhatsApp enquanto você atende.",
    sub: "Direta e sem enrolação: informa preço, oferece horário livre e marca. Três semanas depois, chama o cliente de volta.",
    people: "clientes",
    person: "cliente",
    features: [
      { title: "Tom da barbearia", text: "Informal e objetiva por padrão. Você troca se quiser." },
      { title: "Sem encaixe fantasma", text: "Só oferece horários livres na agenda. Encaixe é decisão sua." },
      { title: "Cliente volta", text: "Vinte e um dias depois do corte, sai o convite para marcar o próximo." },
    ],
    chat: [
      { from: "cliente", text: "Tem horário hoje pra corte e barba?" },
      { from: "assistente", text: "Fala! Corte e barba R$ 70. Hoje tenho 16h e 18h30. Qual?" },
      { from: "cliente", text: "18h30" },
      { from: "assistente", text: "Fechado: hoje, 18h30, corte e barba. Até mais!" },
    ],
    care: "Não promete encaixe fora da agenda.",
  },
  {
    key: "pet",
    slug: "pet",
    label: "Pet",
    eyebrow: "Para pet shops e clínicas veterinárias",
    headline: "Banho, tosa e consulta marcados no WhatsApp, sem tirar o tutor da fila.",
    sub: "A assistente informa serviços e valores, agenda e reconhece urgência: orienta a levar o pet já e avisa a equipe.",
    people: "tutores",
    person: "tutor",
    features: [
      { title: "Fala com o tutor", text: "Vocabulário do ramo: tutor, pet, banho e tosa, vacina, consulta." },
      { title: "Urgência é urgência", text: "Nunca avalia sintomas do animal. Se parecer grave, orienta a ir agora e avisa você." },
      { title: "Vacina e retorno", text: "Noventa dias depois, o tutor recebe o lembrete de retorno." },
    ],
    chat: [
      { from: "cliente", text: "Quanto é banho e tosa pra shih tzu?" },
      { from: "assistente", text: "Olá! Banho e tosa para porte pequeno sai R$ 90. Tenho amanhã às 10h e às 14h. Qual prefere?" },
      { from: "cliente", text: "Amanhã 10h" },
      { from: "assistente", text: "Reservado: amanhã, 10h, banho e tosa. Traga a carteirinha de vacinação. Até amanhã!" },
    ],
    care: "Nunca avalia sintomas do animal nem indica remédio.",
  },
  {
    key: "advocacia",
    slug: "advocacia",
    label: "Advocacia",
    eyebrow: "Para escritórios de advocacia",
    headline: "Triagem e agendamento no WhatsApp, sem opinar sobre o caso.",
    sub: "A assistente colhe o assunto em uma frase, informa horários de atendimento e agenda a reunião. A orientação jurídica é sempre do advogado.",
    people: "clientes",
    person: "cliente",
    features: [
      { title: "Formal por padrão", text: "Tom formal já configurado; você ajusta se preferir." },
      { title: "Zero orientação jurídica", text: "Ela nunca opina sobre o caso. Registra o assunto e agenda ou encaminha." },
      { title: "Base de conhecimento", text: "Áreas de atuação, documentos necessários, forma de pagamento: cole e ela responde." },
    ],
    chat: [
      { from: "cliente", text: "Preciso de ajuda com uma rescisão trabalhista" },
      { from: "assistente", text: "Olá. Anotei: rescisão trabalhista. Posso agendar um atendimento com o Dr. Souza na quarta às 10h ou quinta às 16h. Qual horário prefere?" },
      { from: "cliente", text: "Quinta 16h" },
      { from: "assistente", text: "Agendado: quinta, 16h. Traga contrato e comprovantes de pagamento. Até lá." },
    ],
    care: "Nunca dá orientação jurídica nem opina sobre o caso.",
  },
  {
    key: "contabilidade",
    slug: "contabilidade",
    label: "Contabilidade",
    eyebrow: "Para contabilidade e consultoria",
    headline: "Reuniões marcadas e documentos encaminhados pelo WhatsApp.",
    sub: "A assistente organiza a agenda, recebe pedidos e encaminha dúvidas à equipe. Orientação fiscal só com o contador.",
    people: "clientes",
    person: "cliente",
    features: [
      { title: "Reunião sem troca de mensagens", text: "Ela oferece os horários livres e marca." },
      { title: "Sem orientação fiscal", text: "Colhe o assunto e agenda ou encaminha ao responsável." },
      { title: "Lembretes do mês", text: "Convite trimestral para revisar pendências, se você quiser." },
    ],
    chat: [
      { from: "cliente", text: "Preciso falar sobre o imposto de renda da empresa" },
      { from: "assistente", text: "Olá. Anotei: imposto de renda da empresa. Posso agendar com a contadora na terça às 11h ou quarta às 14h?" },
      { from: "cliente", text: "Terça 11h" },
      { from: "assistente", text: "Agendado: terça, 11h. Se puder, envie o balancete por aqui antes. Até lá." },
    ],
    care: "Nunca dá orientação fiscal ou contábil.",
  },
  {
    key: "academia",
    slug: "academias",
    label: "Academias",
    eyebrow: "Para academias e personal trainers",
    headline: "Matrícula, aula experimental e horários respondidos na hora.",
    sub: "A assistente informa planos, marca aula experimental e chama de volta quem sumiu dos treinos.",
    people: "alunos",
    person: "aluno",
    features: [
      { title: "Aula experimental agendada", text: "Oferece horários livres e marca a primeira aula." },
      { title: "Sem treino nem dieta", text: "Dúvidas de saúde e prescrição vão para a equipe." },
      { title: "Sumiu? Ela chama", text: "Duas semanas sem treinar e o aluno recebe um convite para voltar." },
    ],
    chat: [
      { from: "cliente", text: "Quanto é o plano mensal? Tem aula experimental?" },
      { from: "assistente", text: "Oi! O mensal é R$ 129 e a aula experimental é grátis. Tenho amanhã às 7h ou 19h. Qual prefere?" },
      { from: "cliente", text: "19h" },
      { from: "assistente", text: "Marcado: amanhã, 19h, aula experimental. Venha com roupa de treino. Te esperamos!" },
    ],
    care: "Não prescreve treino nem dieta.",
  },
];

export function nichePageBySlug(slug: string): NichePage | undefined {
  return NICHE_PAGES.find((n) => n.slug === slug);
}
