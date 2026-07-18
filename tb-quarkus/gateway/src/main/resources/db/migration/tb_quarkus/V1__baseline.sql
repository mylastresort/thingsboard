--
-- PostgreSQL database dump
--

-- Dumped from database version 18.4 (Debian 18.4-1.pgdg13+1)
-- Dumped by pg_dump version 18.4 (Debian 18.4-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: tb_quarkus; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS tb_quarkus;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: claim; Type: TABLE; Schema: tb_quarkus; Owner: -
--

CREATE TABLE tb_quarkus.claim (
    id uuid NOT NULL,
    body character varying(255) NOT NULL,
    created_time bigint NOT NULL,
    tenant_id uuid NOT NULL,
    done boolean DEFAULT false,
    name character varying(255) NOT NULL,
    assignee_id uuid,
    tags jsonb DEFAULT '[]'::jsonb NOT NULL
);


--
-- Name: claim claims_pkey; Type: CONSTRAINT; Schema: tb_quarkus; Owner: -
--

ALTER TABLE ONLY tb_quarkus.claim
    ADD CONSTRAINT claims_pkey PRIMARY KEY (id);


--
-- Name: claim fk_claims_assignee_id; Type: FK CONSTRAINT; Schema: tb_quarkus; Owner: -
--

ALTER TABLE ONLY tb_quarkus.claim
    ADD CONSTRAINT fk_claims_assignee_id FOREIGN KEY (assignee_id) REFERENCES public.tb_user(id);


--
-- Name: claim fk_claims_tenant_id; Type: FK CONSTRAINT; Schema: tb_quarkus; Owner: -
--

ALTER TABLE ONLY tb_quarkus.claim
    ADD CONSTRAINT fk_claims_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenant(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

