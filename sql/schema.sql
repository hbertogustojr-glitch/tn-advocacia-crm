CREATE TABLE organizations (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(160) NOT NULL,
    document_number VARCHAR(32) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    organization_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(160) NOT NULL,
    email VARCHAR(180) NOT NULL,
    role VARCHAR(40) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_users_org_email UNIQUE (organization_id, email),
    CONSTRAINT fk_users_organization FOREIGN KEY (organization_id) REFERENCES organizations(id)
);

CREATE TABLE clients (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    organization_id BIGINT UNSIGNED NOT NULL,
    display_name VARCHAR(180) NOT NULL,
    person_type VARCHAR(20) NOT NULL DEFAULT 'unknown',
    document_number VARCHAR(32) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_clients_org_document UNIQUE (organization_id, document_number),
    CONSTRAINT fk_clients_organization FOREIGN KEY (organization_id) REFERENCES organizations(id)
);

CREATE TABLE contacts (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    organization_id BIGINT UNSIGNED NOT NULL,
    channel VARCHAR(24) NOT NULL,
    channel_identifier VARCHAR(80) NOT NULL,
    phone_number VARCHAR(32) NULL,
    display_name VARCHAR(180) NULL,
    external_contact_id VARCHAR(120) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_contacts_channel_identifier UNIQUE (organization_id, channel, channel_identifier),
    CONSTRAINT fk_contacts_organization FOREIGN KEY (organization_id) REFERENCES organizations(id)
);

CREATE TABLE client_contacts (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    client_id BIGINT UNSIGNED NOT NULL,
    contact_id BIGINT UNSIGNED NOT NULL,
    relationship_label VARCHAR(80) NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_client_contacts_pair UNIQUE (client_id, contact_id),
    CONSTRAINT fk_client_contacts_client FOREIGN KEY (client_id) REFERENCES clients(id),
    CONSTRAINT fk_client_contacts_contact FOREIGN KEY (contact_id) REFERENCES contacts(id)
);

CREATE TABLE legal_matters (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    organization_id BIGINT UNSIGNED NOT NULL,
    client_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(220) NOT NULL,
    matter_type VARCHAR(80) NULL,
    process_number VARCHAR(80) NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_legal_matters_process UNIQUE (organization_id, process_number),
    CONSTRAINT fk_legal_matters_organization FOREIGN KEY (organization_id) REFERENCES organizations(id),
    CONSTRAINT fk_legal_matters_client FOREIGN KEY (client_id) REFERENCES clients(id)
);

CREATE TABLE conversations (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    organization_id BIGINT UNSIGNED NOT NULL,
    contact_id BIGINT UNSIGNED NOT NULL,
    client_id BIGINT UNSIGNED NULL,
    legal_matter_id BIGINT UNSIGNED NULL,
    channel VARCHAR(24) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    assigned_user_id BIGINT UNSIGNED NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_conversations_lookup (organization_id, contact_id, status),
    CONSTRAINT fk_conversations_organization FOREIGN KEY (organization_id) REFERENCES organizations(id),
    CONSTRAINT fk_conversations_contact FOREIGN KEY (contact_id) REFERENCES contacts(id),
    CONSTRAINT fk_conversations_client FOREIGN KEY (client_id) REFERENCES clients(id),
    CONSTRAINT fk_conversations_legal_matter FOREIGN KEY (legal_matter_id) REFERENCES legal_matters(id),
    CONSTRAINT fk_conversations_assigned_user FOREIGN KEY (assigned_user_id) REFERENCES users(id)
);

CREATE TABLE messages (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    conversation_id BIGINT UNSIGNED NOT NULL,
    provider VARCHAR(40) NOT NULL,
    external_message_id VARCHAR(160) NULL,
    direction VARCHAR(16) NOT NULL,
    sender_type VARCHAR(24) NOT NULL,
    message_type VARCHAR(24) NOT NULL DEFAULT 'text',
    body TEXT NOT NULL,
    sent_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_messages_conversation_sent_at (conversation_id, sent_at),
    CONSTRAINT uq_messages_provider_external UNIQUE (provider, external_message_id),
    CONSTRAINT fk_messages_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id)
);

CREATE TABLE ai_decisions (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    conversation_id BIGINT UNSIGNED NOT NULL,
    inbound_message_id BIGINT UNSIGNED NOT NULL,
    action VARCHAR(32) NOT NULL,
    confidence DECIMAL(5,4) NOT NULL,
    reason VARCHAR(500) NULL,
    model_name VARCHAR(80) NULL,
    prompt_version VARCHAR(40) NOT NULL DEFAULT 'legal-v1',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_ai_decisions_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    CONSTRAINT fk_ai_decisions_inbound_message FOREIGN KEY (inbound_message_id) REFERENCES messages(id)
);

CREATE TABLE handoff_requests (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    conversation_id BIGINT UNSIGNED NOT NULL,
    requested_by_message_id BIGINT UNSIGNED NOT NULL,
    reason TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'open',
    assigned_user_id BIGINT UNSIGNED NULL,
    resolved_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_handoff_status (status, created_at),
    CONSTRAINT fk_handoff_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    CONSTRAINT fk_handoff_message FOREIGN KEY (requested_by_message_id) REFERENCES messages(id),
    CONSTRAINT fk_handoff_assigned_user FOREIGN KEY (assigned_user_id) REFERENCES users(id)
);

CREATE TABLE follow_up_tasks (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    conversation_id BIGINT UNSIGNED NOT NULL,
    contact_id BIGINT UNSIGNED NOT NULL,
    trigger_message_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    reason VARCHAR(220) NOT NULL,
    scheduled_for DATETIME NOT NULL,
    sent_message_id BIGINT UNSIGNED NULL,
    canceled_at DATETIME NULL,
    sent_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_follow_up_due (status, scheduled_for),
    INDEX ix_follow_up_conversation (conversation_id, status),
    CONSTRAINT fk_follow_up_conversation FOREIGN KEY (conversation_id) REFERENCES conversations(id),
    CONSTRAINT fk_follow_up_contact FOREIGN KEY (contact_id) REFERENCES contacts(id),
    CONSTRAINT fk_follow_up_trigger_message FOREIGN KEY (trigger_message_id) REFERENCES messages(id),
    CONSTRAINT fk_follow_up_sent_message FOREIGN KEY (sent_message_id) REFERENCES messages(id)
);

CREATE TABLE knowledge_articles (
    id BIGINT UNSIGNED PRIMARY KEY AUTO_INCREMENT,
    organization_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(220) NOT NULL,
    category VARCHAR(80) NULL,
    content TEXT NOT NULL,
    approved_by_user_id BIGINT UNSIGNED NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_knowledge_active (organization_id, is_active, category),
    CONSTRAINT fk_knowledge_organization FOREIGN KEY (organization_id) REFERENCES organizations(id),
    CONSTRAINT fk_knowledge_approved_by FOREIGN KEY (approved_by_user_id) REFERENCES users(id)
);
