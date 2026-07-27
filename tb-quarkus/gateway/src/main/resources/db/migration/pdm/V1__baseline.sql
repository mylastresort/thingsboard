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
-- Name: tb_quarkus_pdm; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA IF NOT EXISTS tb_quarkus_pdm;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: device_errors; Type: TABLE; Schema: tb_quarkus_pdm; Owner: -
--

CREATE TABLE tb_quarkus_pdm.device_errors (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    device_id uuid NOT NULL,
    error_time timestamp without time zone NOT NULL,
    error_code character varying(100) NOT NULL,
    error_type character varying(255),
    error_severity character varying(50),
    error_description text,
    component character varying(255),
    recovery_time timestamp without time zone,
    was_auto_recovered boolean DEFAULT false,
    led_to_failure boolean DEFAULT false,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT now(),
    created_time bigint
);


--
-- Name: device_failures; Type: TABLE; Schema: tb_quarkus_pdm; Owner: -
--

CREATE TABLE tb_quarkus_pdm.device_failures (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    device_id uuid NOT NULL,
    failure_time timestamp without time zone NOT NULL,
    detection_time timestamp without time zone,
    resolved_time timestamp without time zone,
    failure_type character varying(255) NOT NULL,
    failure_severity character varying(50),
    failure_description text,
    root_cause character varying(255) NOT NULL,
    downtime_hours double precision,
    repair_cost double precision,
    replaced_parts jsonb,
    maintenance_actions jsonb,
    was_predicted boolean DEFAULT false,
    prediction_lead_time_hours double precision,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT now(),
    created_time bigint
);


--
-- Name: device_maintenance; Type: TABLE; Schema: tb_quarkus_pdm; Owner: -
--

CREATE TABLE tb_quarkus_pdm.device_maintenance (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    device_id uuid NOT NULL,
    maintenance_type character varying(100) NOT NULL,
    maintenance_date timestamp without time zone NOT NULL,
    duration_hours double precision,
    cost double precision,
    technician character varying(255),
    description text,
    parts_replaced character varying(255) NOT NULL,
    actions_performed jsonb,
    next_maintenance_date timestamp without time zone,
    metadata jsonb,
    created_at timestamp without time zone DEFAULT now(),
    created_time bigint
);


--
-- Name: predictions; Type: TABLE; Schema: tb_quarkus_pdm; Owner: -
--

CREATE TABLE tb_quarkus_pdm.predictions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    model_id uuid NOT NULL,
    created_time bigint NOT NULL,
    created_at timestamp without time zone DEFAULT now(),
    prediction_time timestamp without time zone DEFAULT now() NOT NULL,
    prediction_type character varying(100) NOT NULL,
    prediction_value jsonb
);


--
-- Name: predictive_maintenance_config; Type: TABLE; Schema: tb_quarkus_pdm; Owner: -
--

CREATE TABLE tb_quarkus_pdm.predictive_maintenance_config (
    id uuid NOT NULL,
    name character varying(255) NOT NULL,
    created_time bigint NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    attributes jsonb NOT NULL,
    forecast_algorithm character varying(255) DEFAULT 'ARIMA'::character varying NOT NULL,
    forecast_start_date bigint DEFAULT 0 NOT NULL,
    forecast_end_date bigint DEFAULT 0 NOT NULL,
    anomaly_algorithm character varying(255) DEFAULT 'THRESHOLD'::character varying NOT NULL,
    anomaly_start_date bigint DEFAULT 0 NOT NULL,
    anomaly_end_date bigint DEFAULT 0 NOT NULL,
    view_preferences jsonb DEFAULT '{"selectedViews": ["forecast", "anomalies"]}'::jsonb,
    additional_data jsonb DEFAULT '{}'::jsonb
);


--
-- Name: predictive_model_load_model_config; Type: TABLE; Schema: tb_quarkus_pdm; Owner: -
--

CREATE TABLE tb_quarkus_pdm.predictive_model_load_model_config (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    name character varying(255) NOT NULL,
    config jsonb NOT NULL
);


--
-- Name: device_errors device_errors_pkey; Type: CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.device_errors
    ADD CONSTRAINT device_errors_pkey PRIMARY KEY (id);


--
-- Name: device_failures device_failures_pkey; Type: CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.device_failures
    ADD CONSTRAINT device_failures_pkey PRIMARY KEY (id);


--
-- Name: device_maintenance device_maintenance_pkey; Type: CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.device_maintenance
    ADD CONSTRAINT device_maintenance_pkey PRIMARY KEY (id);


--
-- Name: predictions predictions_pkey; Type: CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.predictions
    ADD CONSTRAINT predictions_pkey PRIMARY KEY (id);


--
-- Name: predictive_maintenance_config predictive_maintenance_config_pkey; Type: CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.predictive_maintenance_config
    ADD CONSTRAINT predictive_maintenance_config_pkey PRIMARY KEY (id);


--
-- Name: predictive_model_load_model_config predictive_model_load_model_config_pkey; Type: CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.predictive_model_load_model_config
    ADD CONSTRAINT predictive_model_load_model_config_pkey PRIMARY KEY (id);


--
-- Name: idx_errors_device_id; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_errors_device_id ON tb_quarkus_pdm.device_errors USING btree (device_id);


--
-- Name: idx_errors_error_code; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_errors_error_code ON tb_quarkus_pdm.device_errors USING btree (error_code);


--
-- Name: idx_errors_error_time; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_errors_error_time ON tb_quarkus_pdm.device_errors USING btree (error_time DESC);


--
-- Name: idx_errors_error_type; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_errors_error_type ON tb_quarkus_pdm.device_errors USING btree (error_type);


--
-- Name: idx_failures_device_id; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_failures_device_id ON tb_quarkus_pdm.device_failures USING btree (device_id);


--
-- Name: idx_failures_failure_time; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_failures_failure_time ON tb_quarkus_pdm.device_failures USING btree (failure_time DESC);


--
-- Name: idx_failures_failure_type; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_failures_failure_type ON tb_quarkus_pdm.device_failures USING btree (failure_type);


--
-- Name: idx_maintenance_date; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_maintenance_date ON tb_quarkus_pdm.device_maintenance USING btree (maintenance_date DESC);


--
-- Name: idx_maintenance_device_id; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_maintenance_device_id ON tb_quarkus_pdm.device_maintenance USING btree (device_id);


--
-- Name: idx_pm_config_created_time; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_pm_config_created_time ON tb_quarkus_pdm.predictive_maintenance_config USING btree (created_time DESC);


--
-- Name: idx_pm_config_device_id; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_pm_config_device_id ON tb_quarkus_pdm.predictive_maintenance_config USING btree (device_id);


--
-- Name: idx_pm_config_tenant_id; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_pm_config_tenant_id ON tb_quarkus_pdm.predictive_maintenance_config USING btree (tenant_id);


--
-- Name: idx_predictions_model_id; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_predictions_model_id ON tb_quarkus_pdm.predictions USING btree (model_id);


--
-- Name: idx_predictions_prediction_time; Type: INDEX; Schema: tb_quarkus_pdm; Owner: -
--

CREATE INDEX idx_predictions_prediction_time ON tb_quarkus_pdm.predictions USING btree (prediction_time DESC);


--
-- Name: device_errors fk_device_errors_device; Type: FK CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.device_errors
    ADD CONSTRAINT fk_device_errors_device FOREIGN KEY (device_id) REFERENCES public.device(id) ON DELETE CASCADE;


--
-- Name: device_failures fk_device_failures_device; Type: FK CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.device_failures
    ADD CONSTRAINT fk_device_failures_device FOREIGN KEY (device_id) REFERENCES public.device(id) ON DELETE CASCADE;


--
-- Name: device_maintenance fk_device_maintenance_device; Type: FK CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.device_maintenance
    ADD CONSTRAINT fk_device_maintenance_device FOREIGN KEY (device_id) REFERENCES public.device(id) ON DELETE CASCADE;


--
-- Name: predictive_maintenance_config fk_pm_config_device_id; Type: FK CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.predictive_maintenance_config
    ADD CONSTRAINT fk_pm_config_device_id FOREIGN KEY (device_id) REFERENCES public.device(id) ON DELETE CASCADE;


--
-- Name: predictive_maintenance_config fk_pm_config_tenant_id; Type: FK CONSTRAINT; Schema: tb_quarkus_pdm; Owner: -
--

ALTER TABLE ONLY tb_quarkus_pdm.predictive_maintenance_config
    ADD CONSTRAINT fk_pm_config_tenant_id FOREIGN KEY (tenant_id) REFERENCES public.tenant(id) ON DELETE CASCADE;


--
-- NOTE: predictions_model_id_fkey intentionally omitted.
-- Predictions are historical data that must survive model config deletion.


--
-- PostgreSQL database dump complete
--

