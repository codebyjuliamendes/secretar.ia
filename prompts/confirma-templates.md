# Templates de Confirmação (Sem LLM)

Estes templates são usados diretamente no N8n (via nó Set/Expression) e não passam pelo modelo de IA. A escolha de qual usar deve ser feita através de um hash rotativo, por exemplo: `hash(data + telefone) % 3` para não parecer um bot repetitivo caso o paciente frequente muito a clínica.

O objetivo é apenas confirmar a consulta agendada no dia anterior.

---

### Template 1
Olá {{nome_paciente}}! Aqui é da {{NOME_CLINICA}}. Passando apenas para confirmar a sua consulta amanhã, às {{hora}}, com {{profissional}} para realizar seu procedimento de {{procedimento}}. 

Podemos confirmar sua presença? Responda **SIM** para confirmar ou **NÃO** para desmarcar.

---

### Template 2
Oi {{nome_paciente}}! Estamos ansiosos para te receber amanhã na {{NOME_CLINICA}} às {{hora}}. Sua sessão de {{procedimento}} com {{profissional}} já está devidamente separada. 

Você confirma o seu comparecimento? (Por favor, responda com **SIM** ou **NÃO**).

---

### Template 3
Olá {{nome_paciente}}, tudo bem? A equipe da {{NOME_CLINICA}} te aguarda amanhã às {{hora}} para o seu agendamento de {{procedimento}} com {{profissional}}. 

Para confirmar e garantir a sua vaga na agenda, por favor, nos responda com **SIM** ou **NÃO**. Muito obrigada!
