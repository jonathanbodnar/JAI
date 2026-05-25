// Run once against your Neo4j Aura instance.
// neo4j-cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f constraints.cypher

CREATE CONSTRAINT person_id        IF NOT EXISTS FOR (n:Person)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT company_id       IF NOT EXISTS FOR (n:Company)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT project_id       IF NOT EXISTS FOR (n:Project)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT decision_id      IF NOT EXISTS FOR (n:Decision)      REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT belief_id        IF NOT EXISTS FOR (n:Belief)        REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT pattern_id       IF NOT EXISTS FOR (n:Pattern)       REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT skill_id         IF NOT EXISTS FOR (n:Skill)         REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT conversation_id  IF NOT EXISTS FOR (n:Conversation)  REQUIRE n.id IS UNIQUE;
CREATE CONSTRAINT topic_id         IF NOT EXISTS FOR (n:Topic)         REQUIRE n.id IS UNIQUE;

// Composite: every node is scoped to a user
CREATE INDEX user_scope_person   IF NOT EXISTS FOR (n:Person)   ON (n.user_id);
CREATE INDEX user_scope_company  IF NOT EXISTS FOR (n:Company)  ON (n.user_id);
CREATE INDEX user_scope_project  IF NOT EXISTS FOR (n:Project)  ON (n.user_id);
CREATE INDEX user_scope_decision IF NOT EXISTS FOR (n:Decision) ON (n.user_id);
CREATE INDEX user_scope_belief   IF NOT EXISTS FOR (n:Belief)   ON (n.user_id);
CREATE INDEX user_scope_pattern  IF NOT EXISTS FOR (n:Pattern)  ON (n.user_id);
CREATE INDEX user_scope_topic    IF NOT EXISTS FOR (n:Topic)    ON (n.user_id);
