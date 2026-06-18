INSERT INTO organizations (id, name, status)
VALUES (1, 'Escritorio Modelo', 'active')
ON DUPLICATE KEY UPDATE name = VALUES(name), status = VALUES(status);

INSERT INTO users (organization_id, full_name, email, role, is_active)
VALUES (1, 'Atendente Humano', 'atendimento@example.com', 'attendant', TRUE)
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name), role = VALUES(role), is_active = VALUES(is_active);

INSERT INTO users (organization_id, full_name, email, role, is_active)
VALUES
    (1, 'Camilla', 'camilla@tnadvocacia.local', 'lawyer', TRUE),
    (1, 'Thiago', 'thiago@tnadvocacia.local', 'lawyer', TRUE)
ON DUPLICATE KEY UPDATE full_name = VALUES(full_name), role = VALUES(role), is_active = VALUES(is_active);

INSERT INTO knowledge_articles (organization_id, title, category, content, is_active)
VALUES
(
    1,
    'Resposta inicial padrao',
    'atendimento',
    'Ao receber uma mensagem inicial, cumprimente o cliente, confirme o recebimento e informe que o escritorio verificara as informacoes antes de responder assuntos juridicos especificos.',
    TRUE
),
(
    1,
    'Regra de encaminhamento humano',
    'seguranca',
    'Encaminhe para humano quando a mensagem envolver prazo, audiencia, processo, documento, valores, honorarios, estrategia juridica, urgencia ou insatisfacao.',
    TRUE
);
