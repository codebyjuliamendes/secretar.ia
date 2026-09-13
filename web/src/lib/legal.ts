/**
 * Texto da Política de Privacidade e dos Termos de Uso.
 *
 * IMPORTANTE: é uma redação de partida, escrita para refletir exatamente o que o sistema faz hoje (LGPD,
 * papéis de controlador/operador, subprocessadores e retenção). Antes de publicar, peça a revisão de um
 * advogado: só ele pode validar o texto para o seu caso. Os dados da empresa (razão social, CNPJ e e-mail do
 * encarregado) vêm da configuração do servidor (LEGAL_ENTITY, LEGAL_DOC, PRIVACY_EMAIL); quando vazios, a
 * linha correspondente simplesmente não aparece.
 */

export const LEGAL_UPDATED_AT = "13 de setembro de 2026";

export interface LegalSection {
  title: string;
  paragraphs?: string[];
  bullets?: string[];
}

export function privacySections(contact: string): LegalSection[] {
  return [
    {
      title: "Resumo em uma frase",
      paragraphs: [
        "A Secretar.ia é uma assistente virtual que atende pelo WhatsApp do seu negócio. Para isso, guardamos as conversas, os contatos e a agenda do negócio. Não vendemos dados, não usamos as conversas para anúncios e não treinamos modelos de inteligência artificial com o conteúdo dos seus clientes.",
      ],
    },
    {
      title: "Dois papéis diferentes",
      paragraphs: [
        "Quando o assunto é a conta do negócio (nome, e-mail e senha de quem entra no painel), nós somos o controlador dos dados: decidimos o que fazer com eles para manter o serviço no ar e cobrar por ele.",
        "Quando o assunto são as pessoas atendidas pelo negócio (os contatos que escrevem no WhatsApp), o controlador é o próprio negócio contratante. Nós somos o operador: tratamos esses dados seguindo as instruções dele. Pedidos sobre esses dados devem ser feitos ao negócio, que tem as ferramentas para atender.",
      ],
    },
    {
      title: "Que dados tratamos",
      bullets: [
        "Cadastro de quem usa o painel: nome, e-mail, senha (guardada apenas como hash, nunca em texto) e registros de acesso.",
        "Dados do negócio: nome, WhatsApp, endereço de atendimento, serviços, preços, horários e textos que a equipe cadastra.",
        "Contatos atendidos: nome, telefone, observações escritas pela equipe e histórico de agendamentos.",
        "Conversas do WhatsApp: mensagens recebidas e enviadas, além de áudios e imagens que a pessoa enviar, convertidos em texto para a assistente entender.",
        "Uso do sistema: quantidade de mensagens, tempo de resposta e erros, para medir o plano e investigar problemas.",
        "Pagamento: quando a cobrança é por cartão, o processamento é feito pelo Stripe e não guardamos o número do cartão.",
      ],
    },
    {
      title: "Para que usamos e com qual base legal",
      bullets: [
        "Executar o contrato: responder mensagens, registrar agendamentos, manter agenda e painel funcionando, cobrar a mensalidade.",
        "Legítimo interesse: segurança, prevenção a abuso, registros de auditoria e melhoria do serviço.",
        "Consentimento: mensagens de campanha de retorno, que qualquer pessoa pode recusar escrevendo que não quer mais receber. A recusa vale na hora.",
        "Obrigação legal: guardar registros exigidos por lei e responder autoridades quando obrigados.",
      ],
    },
    {
      title: "Com quem compartilhamos",
      paragraphs: [
        "Só com fornecedores necessários para o serviço funcionar, e apenas com o mínimo necessário:",
      ],
      bullets: [
        "Google (Gemini): processa o texto da conversa para gerar a resposta e transcrever áudios e imagens.",
        "Provedor de conexão com o WhatsApp: entrega e recebe as mensagens do número do negócio.",
        "Provedor de e-mail: envia confirmações, convites e relatórios.",
        "Stripe: processa pagamentos com cartão, quando essa forma é usada.",
        "Google Calendar: apenas se o negócio conectar a agenda dele, e somente para criar e ler compromissos.",
        "Hospedagem e banco de dados, onde o sistema roda.",
      ],
    },
    {
      title: "Transferência internacional",
      paragraphs: [
        "Alguns desses fornecedores processam dados fora do Brasil. A LGPD permite isso quando é necessário para executar o contrato e quando o fornecedor oferece garantias de proteção, que é o caso dos serviços acima.",
      ],
    },
    {
      title: "Por quanto tempo guardamos",
      bullets: [
        "Conversas e agendamentos: enquanto o negócio for cliente, porque são o histórico de trabalho dele.",
        "Registros técnicos de processamento de mensagens: trinta dias.",
        "Registros de auditoria e dados exigidos por lei: pelo prazo legal aplicável.",
        "Encerrada a conta e feita a exportação, os dados são apagados, inclusive conversas, contatos e agenda.",
      ],
    },
    {
      title: "Seus direitos",
      paragraphs: [
        "A LGPD garante confirmação de tratamento, acesso, correção, portabilidade, eliminação, informação sobre compartilhamento e revogação do consentimento.",
        "Se você foi atendido por um negócio que usa a Secretar.ia, fale primeiro com esse negócio: ele é o controlador e consegue corrigir ou apagar seus dados na hora. Você também pode escrever pelo próprio WhatsApp pedindo a exclusão: a assistente registra o pedido, avisa a equipe e para imediatamente de enviar campanhas para você.",
        "Se você é cliente da Secretar.ia, exporte contatos e agendamentos a qualquer momento pelo painel e peça o encerramento da conta em Minha conta. Também respondemos pelo canal abaixo.",
      ],
    },
    {
      title: "Segurança",
      bullets: [
        "Cada conta só enxerga os próprios dados, com verificação em toda requisição.",
        "Senhas guardadas como hash e sessões em cookies que o JavaScript da página não consegue ler.",
        "Tokens de integrações guardados cifrados no banco.",
        "Registro de auditoria das ações sensíveis, com telefones e nomes ocultos nos logs técnicos.",
        "Tráfego por HTTPS e acesso ao banco restrito à aplicação.",
      ],
    },
    {
      title: "Cookies",
      paragraphs: [
        "Usamos apenas cookies necessários para manter você conectado ao painel. Não usamos cookies de publicidade nem rastreadores de terceiros.",
      ],
    },
    {
      title: "Crianças e adolescentes",
      paragraphs: [
        "O painel é para maiores de 18 anos. Se um negócio atende menores, o responsável legal é quem deve autorizar e acompanhar o atendimento pelo WhatsApp.",
      ],
    },
    {
      title: "Mudanças e contato",
      paragraphs: [
        "Se esta política mudar de forma relevante, avisamos os clientes por e-mail e atualizamos a data no topo.",
        contact
          ? `Dúvidas ou pedidos sobre dados pessoais: ${contact}.`
          : "Dúvidas ou pedidos sobre dados pessoais podem ser enviados pelo canal de contato informado no painel.",
      ],
    },
  ] as LegalSection[];
}

export function termsSections(contact: string): LegalSection[] {
  return [
    {
      title: "O que é o serviço",
      paragraphs: [
        "A Secretar.ia é uma assistente virtual que responde no WhatsApp do seu negócio, informa serviços, valores e horários, registra pedidos de agendamento e chama a sua equipe quando alguém pede uma pessoa. O painel traz agenda, contatos, conversas e relatórios.",
      ],
    },
    {
      title: "Conta e liberação",
      bullets: [
        "Qualquer pessoa pode se cadastrar e configurar a conta, sem cartão.",
        "A conta começa aguardando liberação: a assistente só passa a responder quando a nossa equipe libera o plano.",
        "Você é responsável pelo sigilo da sua senha e pelo que sua equipe fizer na conta.",
        "Os dados informados devem ser verdadeiros, inclusive o número de WhatsApp, que deve pertencer ao negócio.",
      ],
    },
    {
      title: "Planos e pagamento",
      bullets: [
        "Os planos diferem pelo volume de mensagens, contatos, membros da equipe e documentos, e os preços vigentes ficam na página de planos.",
        "A cobrança é mensal ou anual, por Pix, boleto ou cartão, conforme combinado.",
        "Passar do volume do plano não interrompe o atendimento: avisamos você e conversamos sobre a faixa seguinte. Só cortamos quando isso for pedido para a sua conta.",
        "Pagamento em atraso pausa o atendimento automático até a regularização. O painel e a exportação continuam acessíveis.",
      ],
    },
    {
      title: "Como você deve usar",
      bullets: [
        "Só envie mensagens para quem tem relação com o seu negócio e espera ser contatado. Disparo em massa para listas compradas é proibido.",
        "Respeite as regras do WhatsApp. A conexão depende de um serviço de terceiro e pode ser bloqueada por eles se essas regras forem quebradas.",
        "Você é o responsável pelos dados das pessoas que atende e pela base legal para falar com elas.",
        "Não use o serviço para conteúdo ilegal, enganoso ou que viole direitos de terceiros.",
      ],
    },
    {
      title: "O que a assistente faz e o que ela não faz",
      bullets: [
        "Ela é automatizada e pode errar. Toda resposta é gerada a partir do que você cadastrou.",
        "Pedidos de agendamento entram como pendentes: quem confirma é a sua equipe.",
        "Ela nunca dá diagnóstico, orientação médica, jurídica, fiscal ou qualquer aconselhamento profissional, e encaminha esses assuntos à sua equipe.",
        "Ela se apresenta como assistente no primeiro contato de cada pessoa, e você pode desligar isso.",
      ],
    },
    {
      title: "Disponibilidade",
      paragraphs: [
        "Trabalhamos para manter o serviço no ar, mas ele depende de terceiros como o WhatsApp, o provedor de inteligência artificial e a hospedagem. Interrupções desses serviços podem afetar o atendimento e não estão sob nosso controle.",
      ],
    },
    {
      title: "Seus dados e os nossos",
      paragraphs: [
        "O conteúdo que você cadastra e as conversas do seu negócio são seus. Nós apenas os tratamos para entregar o serviço, conforme a Política de Privacidade.",
        "O sistema, a marca e o código são nossos e não são licenciados para cópia ou revenda.",
      ],
    },
    {
      title: "Encerramento",
      bullets: [
        "Você pode encerrar quando quiser, pedindo em Minha conta. Exporte antes contatos e agendamentos em planilha.",
        "Podemos encerrar contas que violem estes termos ou fiquem inadimplentes, avisando por e-mail.",
        "Encerrada a conta, os dados são apagados conforme a Política de Privacidade.",
      ],
    },
    {
      title: "Limites de responsabilidade",
      paragraphs: [
        "Não respondemos por perdas indiretas, lucros cessantes ou decisões tomadas apenas com base em uma resposta automática. Nossa responsabilidade, quando houver, fica limitada ao valor pago nos últimos três meses.",
      ],
    },
    {
      title: "Mudanças e contato",
      paragraphs: [
        "Mudanças relevantes nestes termos são avisadas por e-mail com antecedência razoável.",
        contact ? `Fale com a gente: ${contact}.` : "Fale com a gente pelo canal de contato informado no painel.",
        "Estes termos são regidos pelas leis brasileiras.",
      ],
    },
  ] as LegalSection[];
}
