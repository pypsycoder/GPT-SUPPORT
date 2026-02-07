--
-- PostgreSQL database dump
--

-- Dumped from database version 17.5
-- Dumped by pg_dump version 17.5

-- Started on 2026-02-07 20:58:56

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

ALTER TABLE IF EXISTS ONLY vitals.weight_measurements DROP CONSTRAINT IF EXISTS weight_measurements_user_id_fkey;
ALTER TABLE IF EXISTS ONLY vitals.pulse_measurements DROP CONSTRAINT IF EXISTS pulse_measurements_user_id_fkey;
ALTER TABLE IF EXISTS ONLY vitals.water_intake DROP CONSTRAINT IF EXISTS fk_water_intake_user_id_users;
ALTER TABLE IF EXISTS ONLY vitals.bp_measurements DROP CONSTRAINT IF EXISTS bp_measurements_user_id_fkey;
ALTER TABLE IF EXISTS ONLY scales.scale_results DROP CONSTRAINT IF EXISTS scale_results_user_id_fkey;
ALTER TABLE IF EXISTS ONLY scales.responses DROP CONSTRAINT IF EXISTS responses_user_id_fkey;
ALTER TABLE IF EXISTS ONLY scales.drafts DROP CONSTRAINT IF EXISTS drafts_user_id_fkey;
ALTER TABLE IF EXISTS ONLY education.practices DROP CONSTRAINT IF EXISTS practices_lesson_id_fkey;
ALTER TABLE IF EXISTS ONLY education.practice_logs DROP CONSTRAINT IF EXISTS practice_logs_user_id_fkey;
ALTER TABLE IF EXISTS ONLY education.practice_logs DROP CONSTRAINT IF EXISTS practice_logs_practice_id_fkey;
ALTER TABLE IF EXISTS ONLY education.lesson_tests DROP CONSTRAINT IF EXISTS lesson_tests_lesson_fk;
ALTER TABLE IF EXISTS ONLY education.lesson_test_results DROP CONSTRAINT IF EXISTS lesson_test_results_test_fk;
ALTER TABLE IF EXISTS ONLY education.lesson_test_questions DROP CONSTRAINT IF EXISTS lesson_test_questions_test_fk;
ALTER TABLE IF EXISTS ONLY education.lesson_progress DROP CONSTRAINT IF EXISTS lesson_progress_lesson_fk;
ALTER TABLE IF EXISTS ONLY education.lesson_cards DROP CONSTRAINT IF EXISTS lesson_cards_lesson_id_fkey;
DROP INDEX IF EXISTS vitals.ix_weight_measurements_session_id;
DROP INDEX IF EXISTS vitals.ix_weight_measurements_measured_at;
DROP INDEX IF EXISTS vitals.ix_water_intake_session_id;
DROP INDEX IF EXISTS vitals.ix_water_intake_measured_at;
DROP INDEX IF EXISTS vitals.ix_pulse_measurements_session_id;
DROP INDEX IF EXISTS vitals.ix_pulse_measurements_measured_at;
DROP INDEX IF EXISTS vitals.ix_bp_measurements_session_id;
DROP INDEX IF EXISTS vitals.ix_bp_measurements_measured_at;
DROP INDEX IF EXISTS users.ix_users_users_telegram_id;
DROP INDEX IF EXISTS users.ix_users_patient_token;
DROP INDEX IF EXISTS scales.ix_scale_results_user_id;
DROP INDEX IF EXISTS scales.ix_scale_results_scale_code;
DROP INDEX IF EXISTS scales.ix_scale_results_measured_at;
DROP INDEX IF EXISTS education.lesson_tests_lesson_idx;
DROP INDEX IF EXISTS education.lesson_tests_code_uidx;
DROP INDEX IF EXISTS education.lesson_test_results_token_idx;
DROP INDEX IF EXISTS education.lesson_test_results_quiz_token_idx;
DROP INDEX IF EXISTS education.lesson_test_questions_test_idx;
DROP INDEX IF EXISTS education.lesson_test_questions_order_uidx;
DROP INDEX IF EXISTS education.lesson_progress_patient_lesson_uidx;
DROP INDEX IF EXISTS education.lesson_progress_patient_idx;
DROP INDEX IF EXISTS education.lesson_progress_lesson_idx;
DROP INDEX IF EXISTS education.idx_practices_lesson_id;
DROP INDEX IF EXISTS education.idx_practice_logs_user_id;
DROP INDEX IF EXISTS education.idx_practice_logs_practice_id;
DROP INDEX IF EXISTS education.idx_lesson_cards_lesson_id;
ALTER TABLE IF EXISTS ONLY vitals.weight_measurements DROP CONSTRAINT IF EXISTS weight_measurements_pkey;
ALTER TABLE IF EXISTS ONLY vitals.pulse_measurements DROP CONSTRAINT IF EXISTS pulse_measurements_pkey;
ALTER TABLE IF EXISTS ONLY vitals.water_intake DROP CONSTRAINT IF EXISTS pk_water_intake;
ALTER TABLE IF EXISTS ONLY vitals.bp_measurements DROP CONSTRAINT IF EXISTS bp_measurements_pkey;
ALTER TABLE IF EXISTS ONLY users.users DROP CONSTRAINT IF EXISTS users_pkey;
ALTER TABLE IF EXISTS ONLY scales.scale_results DROP CONSTRAINT IF EXISTS scale_results_pkey;
ALTER TABLE IF EXISTS ONLY scales.responses DROP CONSTRAINT IF EXISTS responses_pkey;
ALTER TABLE IF EXISTS ONLY scales.drafts DROP CONSTRAINT IF EXISTS drafts_pkey;
ALTER TABLE IF EXISTS ONLY public.alembic_version DROP CONSTRAINT IF EXISTS alembic_version_pkey;
ALTER TABLE IF EXISTS ONLY education.practices DROP CONSTRAINT IF EXISTS practices_pkey;
ALTER TABLE IF EXISTS ONLY education.practice_logs DROP CONSTRAINT IF EXISTS practice_logs_pkey;
ALTER TABLE IF EXISTS ONLY education.lessons DROP CONSTRAINT IF EXISTS lessons_pkey;
ALTER TABLE IF EXISTS ONLY education.lessons DROP CONSTRAINT IF EXISTS lessons_code_key;
ALTER TABLE IF EXISTS ONLY education.lesson_tests DROP CONSTRAINT IF EXISTS lesson_tests_pkey;
ALTER TABLE IF EXISTS ONLY education.lesson_test_results DROP CONSTRAINT IF EXISTS lesson_test_results_pkey;
ALTER TABLE IF EXISTS ONLY education.lesson_test_questions DROP CONSTRAINT IF EXISTS lesson_test_questions_pkey;
ALTER TABLE IF EXISTS ONLY education.lesson_progress DROP CONSTRAINT IF EXISTS lesson_progress_pkey;
ALTER TABLE IF EXISTS ONLY education.lesson_cards DROP CONSTRAINT IF EXISTS lesson_cards_pkey;
ALTER TABLE IF EXISTS users.users ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS scales.responses ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS scales.drafts ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.practices ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.practice_logs ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.lessons ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.lesson_tests ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.lesson_test_results ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.lesson_test_questions ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.lesson_progress ALTER COLUMN id DROP DEFAULT;
ALTER TABLE IF EXISTS education.lesson_cards ALTER COLUMN id DROP DEFAULT;
DROP TABLE IF EXISTS vitals.weight_measurements;
DROP TABLE IF EXISTS vitals.water_intake;
DROP TABLE IF EXISTS vitals.pulse_measurements;
DROP TABLE IF EXISTS vitals.bp_measurements;
DROP SEQUENCE IF EXISTS users.users_id_seq;
DROP TABLE IF EXISTS users.users;
DROP TABLE IF EXISTS scales.scale_results;
DROP SEQUENCE IF EXISTS scales.responses_id_seq;
DROP TABLE IF EXISTS scales.responses;
DROP SEQUENCE IF EXISTS scales.drafts_id_seq;
DROP TABLE IF EXISTS scales.drafts;
DROP TABLE IF EXISTS public.alembic_version;
DROP SEQUENCE IF EXISTS education.practices_id_seq;
DROP TABLE IF EXISTS education.practices;
DROP SEQUENCE IF EXISTS education.practice_logs_id_seq;
DROP TABLE IF EXISTS education.practice_logs;
DROP SEQUENCE IF EXISTS education.lessons_id_seq;
DROP TABLE IF EXISTS education.lessons;
DROP SEQUENCE IF EXISTS education.lesson_tests_id_seq;
DROP TABLE IF EXISTS education.lesson_tests;
DROP SEQUENCE IF EXISTS education.lesson_test_results_id_seq;
DROP TABLE IF EXISTS education.lesson_test_results;
DROP SEQUENCE IF EXISTS education.lesson_test_questions_id_seq;
DROP TABLE IF EXISTS education.lesson_test_questions;
DROP SEQUENCE IF EXISTS education.lesson_progress_id_seq;
DROP TABLE IF EXISTS education.lesson_progress;
DROP SEQUENCE IF EXISTS education.lesson_cards_id_seq;
DROP TABLE IF EXISTS education.lesson_cards;
DROP SCHEMA IF EXISTS vitals;
DROP SCHEMA IF EXISTS users;
DROP SCHEMA IF EXISTS scales;
DROP SCHEMA IF EXISTS education;
--
-- TOC entry 9 (class 2615 OID 18429)
-- Name: education; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA education;


ALTER SCHEMA education OWNER TO postgres;

--
-- TOC entry 7 (class 2615 OID 18331)
-- Name: scales; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA scales;


ALTER SCHEMA scales OWNER TO postgres;

--
-- TOC entry 6 (class 2615 OID 18330)
-- Name: users; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA users;


ALTER SCHEMA users OWNER TO postgres;

--
-- TOC entry 8 (class 2615 OID 18332)
-- Name: vitals; Type: SCHEMA; Schema: -; Owner: postgres
--

CREATE SCHEMA vitals;


ALTER SCHEMA vitals OWNER TO postgres;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 234 (class 1259 OID 18446)
-- Name: lesson_cards; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.lesson_cards (
    id integer NOT NULL,
    lesson_id integer NOT NULL,
    order_index integer DEFAULT 0,
    card_type character varying(30) DEFAULT 'text'::character varying,
    content_md text NOT NULL
);


ALTER TABLE education.lesson_cards OWNER TO postgres;

--
-- TOC entry 233 (class 1259 OID 18445)
-- Name: lesson_cards_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.lesson_cards_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.lesson_cards_id_seq OWNER TO postgres;

--
-- TOC entry 5127 (class 0 OID 0)
-- Dependencies: 233
-- Name: lesson_cards_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.lesson_cards_id_seq OWNED BY education.lesson_cards.id;


--
-- TOC entry 240 (class 1259 OID 18579)
-- Name: lesson_progress; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.lesson_progress (
    id integer NOT NULL,
    patient_token character varying(64) NOT NULL,
    lesson_id integer NOT NULL,
    last_card_index integer DEFAULT 0 NOT NULL,
    is_completed boolean DEFAULT false NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE education.lesson_progress OWNER TO postgres;

--
-- TOC entry 239 (class 1259 OID 18578)
-- Name: lesson_progress_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.lesson_progress_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.lesson_progress_id_seq OWNER TO postgres;

--
-- TOC entry 5128 (class 0 OID 0)
-- Dependencies: 239
-- Name: lesson_progress_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.lesson_progress_id_seq OWNED BY education.lesson_progress.id;


--
-- TOC entry 246 (class 1259 OID 18637)
-- Name: lesson_test_questions; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.lesson_test_questions (
    id integer NOT NULL,
    test_id integer NOT NULL,
    order_index integer NOT NULL,
    question_text text NOT NULL,
    option_1 text NOT NULL,
    option_2 text NOT NULL,
    option_3 text NOT NULL,
    option_4 text NOT NULL,
    correct_option integer NOT NULL,
    is_active boolean DEFAULT true NOT NULL
);


ALTER TABLE education.lesson_test_questions OWNER TO postgres;

--
-- TOC entry 245 (class 1259 OID 18636)
-- Name: lesson_test_questions_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.lesson_test_questions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.lesson_test_questions_id_seq OWNER TO postgres;

--
-- TOC entry 5129 (class 0 OID 0)
-- Dependencies: 245
-- Name: lesson_test_questions_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.lesson_test_questions_id_seq OWNED BY education.lesson_test_questions.id;


--
-- TOC entry 242 (class 1259 OID 18597)
-- Name: lesson_test_results; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.lesson_test_results (
    id integer NOT NULL,
    test_id integer NOT NULL,
    patient_token character varying(64) NOT NULL,
    score numeric DEFAULT 0 NOT NULL,
    max_score numeric DEFAULT 0 NOT NULL,
    passed boolean DEFAULT false NOT NULL,
    answers_json jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE education.lesson_test_results OWNER TO postgres;

--
-- TOC entry 241 (class 1259 OID 18596)
-- Name: lesson_test_results_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.lesson_test_results_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.lesson_test_results_id_seq OWNER TO postgres;

--
-- TOC entry 5130 (class 0 OID 0)
-- Dependencies: 241
-- Name: lesson_test_results_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.lesson_test_results_id_seq OWNED BY education.lesson_test_results.id;


--
-- TOC entry 244 (class 1259 OID 18617)
-- Name: lesson_tests; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.lesson_tests (
    id integer NOT NULL,
    lesson_id integer NOT NULL,
    code character varying(64) NOT NULL,
    title character varying(255) NOT NULL,
    short_description character varying(512),
    order_index integer DEFAULT 0 NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE education.lesson_tests OWNER TO postgres;

--
-- TOC entry 243 (class 1259 OID 18616)
-- Name: lesson_tests_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.lesson_tests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.lesson_tests_id_seq OWNER TO postgres;

--
-- TOC entry 5131 (class 0 OID 0)
-- Dependencies: 243
-- Name: lesson_tests_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.lesson_tests_id_seq OWNED BY education.lesson_tests.id;


--
-- TOC entry 232 (class 1259 OID 18431)
-- Name: lessons; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.lessons (
    id integer NOT NULL,
    code character varying(100) NOT NULL,
    topic character varying(50) NOT NULL,
    title character varying(255) NOT NULL,
    short_description character varying(500),
    order_index integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);


ALTER TABLE education.lessons OWNER TO postgres;

--
-- TOC entry 231 (class 1259 OID 18430)
-- Name: lessons_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.lessons_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.lessons_id_seq OWNER TO postgres;

--
-- TOC entry 5132 (class 0 OID 0)
-- Dependencies: 231
-- Name: lessons_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.lessons_id_seq OWNED BY education.lessons.id;


--
-- TOC entry 238 (class 1259 OID 18554)
-- Name: practice_logs; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.practice_logs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    practice_id integer NOT NULL,
    performed_at timestamp with time zone DEFAULT now(),
    success boolean DEFAULT true,
    effect_rating integer,
    comment text
);


ALTER TABLE education.practice_logs OWNER TO postgres;

--
-- TOC entry 237 (class 1259 OID 18553)
-- Name: practice_logs_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.practice_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.practice_logs_id_seq OWNER TO postgres;

--
-- TOC entry 5133 (class 0 OID 0)
-- Dependencies: 237
-- Name: practice_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.practice_logs_id_seq OWNED BY education.practice_logs.id;


--
-- TOC entry 236 (class 1259 OID 18537)
-- Name: practices; Type: TABLE; Schema: education; Owner: postgres
--

CREATE TABLE education.practices (
    id integer NOT NULL,
    lesson_id integer NOT NULL,
    title character varying(255) NOT NULL,
    description_md text NOT NULL,
    order_index integer DEFAULT 0,
    is_active boolean DEFAULT true
);


ALTER TABLE education.practices OWNER TO postgres;

--
-- TOC entry 235 (class 1259 OID 18536)
-- Name: practices_id_seq; Type: SEQUENCE; Schema: education; Owner: postgres
--

CREATE SEQUENCE education.practices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE education.practices_id_seq OWNER TO postgres;

--
-- TOC entry 5134 (class 0 OID 0)
-- Dependencies: 235
-- Name: practices_id_seq; Type: SEQUENCE OWNED BY; Schema: education; Owner: postgres
--

ALTER SEQUENCE education.practices_id_seq OWNED BY education.practices.id;


--
-- TOC entry 221 (class 1259 OID 18333)
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


ALTER TABLE public.alembic_version OWNER TO postgres;

--
-- TOC entry 227 (class 1259 OID 18365)
-- Name: drafts; Type: TABLE; Schema: scales; Owner: postgres
--

CREATE TABLE scales.drafts (
    id integer NOT NULL,
    user_id integer NOT NULL,
    scale_code character varying,
    current_index integer,
    answers json,
    started_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE scales.drafts OWNER TO postgres;

--
-- TOC entry 226 (class 1259 OID 18364)
-- Name: drafts_id_seq; Type: SEQUENCE; Schema: scales; Owner: postgres
--

CREATE SEQUENCE scales.drafts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE scales.drafts_id_seq OWNER TO postgres;

--
-- TOC entry 5135 (class 0 OID 0)
-- Dependencies: 226
-- Name: drafts_id_seq; Type: SEQUENCE OWNED BY; Schema: scales; Owner: postgres
--

ALTER SEQUENCE scales.drafts_id_seq OWNED BY scales.drafts.id;


--
-- TOC entry 225 (class 1259 OID 18351)
-- Name: responses; Type: TABLE; Schema: scales; Owner: postgres
--

CREATE TABLE scales.responses (
    id integer NOT NULL,
    user_id integer NOT NULL,
    scale_code character varying NOT NULL,
    version character varying,
    started_at timestamp without time zone,
    completed_at timestamp without time zone,
    raw_answers json,
    result json,
    interpretation character varying
);


ALTER TABLE scales.responses OWNER TO postgres;

--
-- TOC entry 224 (class 1259 OID 18350)
-- Name: responses_id_seq; Type: SEQUENCE; Schema: scales; Owner: postgres
--

CREATE SEQUENCE scales.responses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE scales.responses_id_seq OWNER TO postgres;

--
-- TOC entry 5136 (class 0 OID 0)
-- Dependencies: 224
-- Name: responses_id_seq; Type: SEQUENCE OWNED BY; Schema: scales; Owner: postgres
--

ALTER SEQUENCE scales.responses_id_seq OWNED BY scales.responses.id;


--
-- TOC entry 247 (class 1259 OID 18663)
-- Name: scale_results; Type: TABLE; Schema: scales; Owner: postgres
--

CREATE TABLE scales.scale_results (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    user_id integer NOT NULL,
    scale_code character varying(32) NOT NULL,
    scale_version character varying(16),
    measured_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    result_json json NOT NULL,
    answers_json json NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


ALTER TABLE scales.scale_results OWNER TO postgres;

--
-- TOC entry 223 (class 1259 OID 18339)
-- Name: users; Type: TABLE; Schema: users; Owner: postgres
--

CREATE TABLE users.users (
    id integer NOT NULL,
    full_name character varying,
    age integer,
    gender character varying,
    consent_personal_data boolean DEFAULT false NOT NULL,
    consent_bot_use boolean DEFAULT false NOT NULL,
    telegram_id character varying NOT NULL,
    external_ids json,
    patient_token character varying(64)
);


ALTER TABLE users.users OWNER TO postgres;

--
-- TOC entry 222 (class 1259 OID 18338)
-- Name: users_id_seq; Type: SEQUENCE; Schema: users; Owner: postgres
--

CREATE SEQUENCE users.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE users.users_id_seq OWNER TO postgres;

--
-- TOC entry 5137 (class 0 OID 0)
-- Dependencies: 222
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: users; Owner: postgres
--

ALTER SEQUENCE users.users_id_seq OWNED BY users.users.id;


--
-- TOC entry 228 (class 1259 OID 18378)
-- Name: bp_measurements; Type: TABLE; Schema: vitals; Owner: postgres
--

CREATE TABLE vitals.bp_measurements (
    systolic integer NOT NULL,
    diastolic integer NOT NULL,
    pulse integer,
    context character varying(32) DEFAULT 'na'::character varying NOT NULL,
    id uuid NOT NULL,
    user_id integer NOT NULL,
    session_id uuid,
    measured_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE vitals.bp_measurements OWNER TO postgres;

--
-- TOC entry 229 (class 1259 OID 18393)
-- Name: pulse_measurements; Type: TABLE; Schema: vitals; Owner: postgres
--

CREATE TABLE vitals.pulse_measurements (
    bpm integer NOT NULL,
    context character varying(32) DEFAULT 'na'::character varying NOT NULL,
    id uuid NOT NULL,
    user_id integer NOT NULL,
    session_id uuid,
    measured_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE vitals.pulse_measurements OWNER TO postgres;

--
-- TOC entry 248 (class 1259 OID 18682)
-- Name: water_intake; Type: TABLE; Schema: vitals; Owner: postgres
--

CREATE TABLE vitals.water_intake (
    id uuid NOT NULL,
    user_id integer NOT NULL,
    session_id uuid,
    measured_at timestamp with time zone DEFAULT now() NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    volume_ml integer NOT NULL,
    liquid_type character varying(32),
    context character varying(32) DEFAULT 'na'::character varying NOT NULL
);


ALTER TABLE vitals.water_intake OWNER TO postgres;

--
-- TOC entry 230 (class 1259 OID 18408)
-- Name: weight_measurements; Type: TABLE; Schema: vitals; Owner: postgres
--

CREATE TABLE vitals.weight_measurements (
    weight numeric(6,2) NOT NULL,
    context character varying(32) DEFAULT 'na'::character varying NOT NULL,
    id uuid NOT NULL,
    user_id integer NOT NULL,
    session_id uuid,
    measured_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


ALTER TABLE vitals.weight_measurements OWNER TO postgres;

--
-- TOC entry 4839 (class 2604 OID 18449)
-- Name: lesson_cards id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_cards ALTER COLUMN id SET DEFAULT nextval('education.lesson_cards_id_seq'::regclass);


--
-- TOC entry 4848 (class 2604 OID 18582)
-- Name: lesson_progress id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_progress ALTER COLUMN id SET DEFAULT nextval('education.lesson_progress_id_seq'::regclass);


--
-- TOC entry 4862 (class 2604 OID 18640)
-- Name: lesson_test_questions id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_test_questions ALTER COLUMN id SET DEFAULT nextval('education.lesson_test_questions_id_seq'::regclass);


--
-- TOC entry 4852 (class 2604 OID 18600)
-- Name: lesson_test_results id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_test_results ALTER COLUMN id SET DEFAULT nextval('education.lesson_test_results_id_seq'::regclass);


--
-- TOC entry 4857 (class 2604 OID 18620)
-- Name: lesson_tests id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_tests ALTER COLUMN id SET DEFAULT nextval('education.lesson_tests_id_seq'::regclass);


--
-- TOC entry 4834 (class 2604 OID 18434)
-- Name: lessons id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lessons ALTER COLUMN id SET DEFAULT nextval('education.lessons_id_seq'::regclass);


--
-- TOC entry 4845 (class 2604 OID 18557)
-- Name: practice_logs id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.practice_logs ALTER COLUMN id SET DEFAULT nextval('education.practice_logs_id_seq'::regclass);


--
-- TOC entry 4842 (class 2604 OID 18540)
-- Name: practices id; Type: DEFAULT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.practices ALTER COLUMN id SET DEFAULT nextval('education.practices_id_seq'::regclass);


--
-- TOC entry 4824 (class 2604 OID 18368)
-- Name: drafts id; Type: DEFAULT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.drafts ALTER COLUMN id SET DEFAULT nextval('scales.drafts_id_seq'::regclass);


--
-- TOC entry 4823 (class 2604 OID 18354)
-- Name: responses id; Type: DEFAULT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.responses ALTER COLUMN id SET DEFAULT nextval('scales.responses_id_seq'::regclass);


--
-- TOC entry 4820 (class 2604 OID 18342)
-- Name: users id; Type: DEFAULT; Schema: users; Owner: postgres
--

ALTER TABLE ONLY users.users ALTER COLUMN id SET DEFAULT nextval('users.users_id_seq'::regclass);


--
-- TOC entry 5107 (class 0 OID 18446)
-- Dependencies: 234
-- Data for Name: lesson_cards; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.lesson_cards (id, lesson_id, order_index, card_type, content_md) FROM stdin;
7	1	7	text	## **🌟 Почему важно учиться справляться**\n\nСтрессы — часть жизни. Мы не можем устранить их полностью.  \nНо мы можем научиться реагировать иначе.\n\nКогда мы умеем справляться со стрессом:\n\n✅ Сохраняется ясность ума в сложных ситуациях  \n💪 Укрепляется иммунитет и общее здоровье  \n😌 Снижается тревожность и улучшается настроение  \n🎯 Повышается мотивация заботиться о себе\n\nКаждый маленький шаг в сторону заботы о себе —  \nэто вклад в твоё здоровье и качество жизни.  \n**И это путь, который стоит пройти.**
50	21	1	text	## 😴 Почему сон так важен\n\nСон помогает мозгу и телу восстанавливаться.  \nВо сне нервная система сбрасывает напряжение, а организм “перезагружается”.  \nПри хронической усталости качественный сон становится особенно важным.  \nКогда сон нарушается, падает настроение, память и работоспособность.  \n**Например:** «После плохой ночи весь день будто идёшь против ветра».
51	21	2	text	## 🌙 Почему при ХБП сон часто ломается\n\nТоксины в крови и стресс могут вызывать беспокойство, ночные пробуждения и трудности с засыпанием.  \nКолебания давления, судороги, дискомфорт в ногах тоже мешают сну.  \nПосле ГД тело может быть перевозбуждено или наоборот “обвалено”.  \nЭто естественные реакции организма на нагрузку.  \n**Например:** «Очень устал, а заснуть всё равно не получается».
52	21	3	text	## 🧠 Что происходит в голове\n\nПри усталости мозг не успевает “отключиться”.  \nМысли крутятся, как будто ум не может найти кнопку паузы.  \nМелкие переживания становятся громче.  \nЭто не “нервность”, это перегруз нервной системы.  \n**Например:** «Лёг спать, а в голове сразу тысяча мыслей».
53	21	4	text	## 🔄 Как выглядит нарушение сна\n\nЧеловек долго не может заснуть.  \nИли засыпает быстро, но часто просыпается.  \nИногда сон поверхностный, будто “сон наполовину”.  \nУтром нет ощущения отдыха.  \n**Например:** «Спал 8 часов, а чувство — будто и не спал».
54	21	5	text	## 🌬 Как тело реагирует на плохой сон\n\nПосле слабого сна сердце работает быстрее, внимание хуже, силы ниже.  \nМожет появиться раздражительность, тревога или апатия.  \nТело медленнее включается в повседневные дела.  \nЭто обычная реакция, а не леность.  \n**Например:** «С утра всё падает из рук, будто мозг проснулся позже тела».
55	21	6	text	## 🔧 Маленькие шаги для улучшения сна\n\nЛучше всего работает стабильный вечерний ритуал.  \nТёплый душ, спокойная музыка, мягкий свет — это помогает телу “понять”, что пора спать.  \nПолезно снижать яркость экранов за час до сна.  \nЧем больше спокойствия вечером, тем легче мозгу отключиться.  \n**Например:** «Выключил яркий свет — через 15 минут стал спокойнее».
56	21	7	text	## ⏳ Режим — важная часть\n\nЛожиться и вставать в одно и то же время помогает стабилизировать биоритмы.  \nДаже если сон не идеальный, режим делает его более глубоким.  \nОрганизм любит предсказуемость.  \nМозг быстрее засыпает, когда знает “во сколько пора”.  \n**Например:** «Когда ложусь в одно время, даже мысли вечером тише».
57	21	8	text	## 🧘 Как успокоить мозг перед сном\n\nМедленное дыхание помогает снизить внутреннее напряжение.  \nПопробуйте выдох чуть длиннее вдоха — это мягко выключает стресс-систему.  \nПолезно переключаться на ощущения тела: тепло, тяжесть, расслабление.  \nНе нужно бороться с мыслями — просто дать им пройти мимо.  \n**Например:** «Сделал 6 медленных выдохов — и напряжение спало».
58	21	9	text	## 🚫 Что мешает спать\n\nПоздняя активность, напряжённые разговоры, яркие экраны — всё это “будит” мозг.  \nЛёжа в кровати, лучше не прокручивать новости или проблемы.  \nЕсли мысли не дают уснуть, встаньте, пройдитесь, выпейте тёплый напиток без кофеина.  \nИногда даже небольшая смена положения помогает.  \n**Например:** «Полежал с телефоном — и снова почувствовал внутренний шум».
59	21	10	text	## 🌅 Как понимать, что сон стал лучше\n\nВы быстрее засыпаете и реже просыпаетесь.  \nУтром появляется чуть больше энергии и ясности.  \nНастроение становится стабильнее.  \nДаже если прогресс маленький — это уже движение вперёд.  \n**Например:** «Проснулся и впервые за долгое время почувствовал лёгкость в голове».
39	19	10	text	## 🌱 Как развивать эмоциональную устойчивость\n\nРегулярные маленькие паузы, отдых, простые ритуалы помогают мозгу восстанавливаться.  \nКогда нервная система заряжена, эмоции управляемее.  \nВажно не требовать от себя “не чувствовать”, а учиться мягко проживать.  \nЭмоциональная устойчивость растёт постепенно.  \n**Например:** «Раньше взрывался мгновенно, теперь замечаю момент до вспышки».
60	22	1	text	## 🧩 Что такое копинг?\n\nКопинг — это способы, которыми человек справляется со стрессом. У каждого они свои, и они часто формируются ещё в детстве. Копинги можно менять и тренировать. Важно понимать свои реакции, чтобы выбирать полезные. Например: «Когда тревожно — кто-то замыкается, а кто-то начинает что-то делать».
61	22	2	text	## 🧠 Модель Лазаруса простым языком\n\nЛазарус выделил несколько основных способов реагирования на стресс. Это не “правильные” и “неправильные” реакции — они просто разные. Каждая стратегия может помогать или мешать, в зависимости от ситуации. Главная задача — научиться замечать, как вы реагируете. Например: «Увидел проблему — автоматически начинаю прокручивать варианты».
62	22	3	text	## 🔧 Проблемно-ориентированный копинг\n\nЭто попытка решить проблему: узнать информацию, спланировать шаги, действовать. Этот способ помогает, когда ситуация действительно изменяема. Он снижает тревогу, потому что возвращает ощущение контроля. Но иногда он просто невозможен — и тогда вызывает ещё больше стресса. Например: «Нашёл, кому позвонить, записался — и стало спокойнее».
63	22	4	text	## 💬 Эмоционально-ориентированный копинг\n\nЭта стратегия направлена на то, чтобы снизить внутреннее напряжение. Человек успокаивает себя: дышит, говорит с близким, гуляет, отвлекается. Она полезна, когда проблему прямо сейчас нельзя решить. Так снижается давление на нервную систему. Например: «После плохих новостей выхожу на воздух и просто сижу пару минут».
64	22	5	text	## 🔄 Когнитивный копинг (переосмысление)\n\nЭто способность посмотреть на ситуацию под другим углом. Не “всё плохо”, а “да, трудно, но я могу сделать вот это”. Так уменьшается ощущение безвыходности. Мозг переключается с катастрофизации на реальность. Например: «Вместо “ничего не успею” — “начну с самого простого шага”».
65	22	6	text	## 🛑 Избегающий копинг\n\nЧеловек отказывается думать о проблеме, откладывает дела, уходит в отвлечение. Иногда это помогает переждать перегруз. Но если избегание становится постоянным — проблемы накапливаются. Важно замечать, когда избегание защищает, а когда мешает. Например: «Надо записаться к врачу, но откладываю уже месяц».
66	22	7	text	## 🧱 Защитный копинг (закрыться от эмоций)\n\nЧеловек делает вид, что всё в порядке, даже если внутри плохо. Это помогает не сорваться в тяжёлый момент. Но если постоянно прятать чувства, напряжение растёт. Иногда “показать слабость” — это способ снизить нагрузку. Например: «Говорю “нормально”, а потом весь вечер внутренний ком».
67	22	8	text	## 🤝 Социальный копинг (через поддержку)\n\nОбщение, разговор, просьба о помощи, разделение переживаний. Очень мощный способ восстановления сил. Даже короткая поддержка снижает стресс. Важно выбирать тех, кто умеет слушать, а не давить. Например: «Поговорил с другом — напряжение спало наполовину».
68	22	9	text	## 🧭 Как понять, что копинг помогает\n\nПосле использования стратегии становится легче дышать и думать. Появляется ясность и ощущение “я справлюсь”. Тело расслабляется, мысли становятся с
6	1	6	text	## **🧠 Что помогает справляться со стрессом**\n\nЕсть способы, которые действительно помогают снять напряжение и восстановиться.  \nОни простые — и работают, если делать их регулярно.\n\n😮‍💨 **Замедленное дыхание** — сигнал телу, что опасность прошла  \n💆‍♂️ **Расслабление мышц** — напряжение уходит через тело  \n📒 **Ведение дневника** — помогает "выписать" переживания  \n🗣 **Разговор с близким** — даёт поддержку и ощущение, что вы не один\n\n**Также помогают**:\n\n🌿 Тёплый душ  \n🎶 Спокойная музыка  \n🌤 Прогулка  \n🛌 Полноценный сон\n\nЭто не магия. Это забота о себе.  \nИ даже 5 минут в день — это уже шаг к восстановлению.
92	25	4	text	## 😶 Что происходит с эмоциями\n\nЭмоции становятся слабее или, наоборот, резко вспыхивают.  \nМожет появиться раздражительность, равнодушие или ощущение внутренней пустоты.  \nСложно радоваться, даже если поводы есть.  \nЭто не “характер”, а признак перегрузки.  \n**Например:** «Понимаю, что должен порадоваться, а внутри тишина».
93	25	5	text	## 🧠 Как меняется мышление\n\nМысли становятся тяжелее, появляется чувство безысходности.  \nСложно планировать, принимать решения, начинать дела.  \nВсё кажется “слишком сложным”.  \nЭто признак того, что мозг пытается экономить энергию.  \n**Например:** «Думаю о задаче — и ощущение, будто тяну камень».
94	25	6	text	## 🕳 Что происходит с интересами\n\nТо, что раньше радовало, становится “всё равно”.  \nХобби, общение, любимые занятия теряют вкус.  \nЭто временное состояние, но оно сильно пугает.  \nВажно помнить: это не навсегда.  \n**Например:** «Смотрю любимый фильм и не чувствую ничего».
5	1	5	text	## **🧠 Ошибки в борьбе со стрессом**\n\nКогда стресс становится сильным, мы часто действуем на автомате.  \nИногда это помогает на пару часов — но не решает проблему.\n\n🙈 **Игнорировать стресс** — делать вид, что всё в порядке  \n🤐 **Замыкаться в себе** — избегать общения и поддержки  \n📺 **"Залипать" в сериалы, еду, телефон**  \n😠 **Срываться на близких** — из-за накопленного напряжения\n\nКажется, что это помогает. Но на самом деле — **стресс уходит внутрь**, накапливается и усиливается.\n\nЭти реакции — понятны и часты.  \nНо мы можем научиться действовать по-другому: мягче, осознаннее, с заботой к себе.
40	20	1	text	## 😟 1. Что такое тревога?\n\nТревога — это сигнал мозга о возможной опасности, даже если угрозы нет. Она помогает нам быть внимательнее и собраннее. Но когда тревога возникает слишком часто, она начинает мешать. Важно помнить: тревога — это не слабость, а нормальная реакция тела. Например: «Идёте на ГД, и внутри уже шумит — хотя всё обычно проходит нормально».
41	20	2	text	## 🔍 2. Зачем человеку тревога?\n\nТревога поднимает внимание и помогает быстрее реагировать. Она защищает нас, когда что-то действительно может пойти не так. Но иногда система безопасности “срабатывает” слишком рано. Это нормально, особенно при хроническом заболевании. Например: «Врач сказал “придёте через неделю”, и вы сразу начинаете прокручивать варианты, что могло быть не так».
42	20	3	text	## 💓 3. Как тревога ощущается в теле?\n\nСердцебиение, дрожь, напряжение, одышка — частые телесные признаки тревоги. Появляется ком в горле, сложно вдохнуть полной грудью. Иногда ощущение, будто “всё внутри сжалось”. Это просто активировалась система защиты, даже если угрозы нет. Например: «Лежите на диализе, всё спокойно, а тело будто само собой напрягается».
43	20	4	text	## 🧠 4. Что происходит в голове?\n\nМысли становятся быстрыми и беспокойными. Обычные ситуации кажутся “хуже, чем есть”. Появляется ощущение, что вы что-то упустили или не заметили. Это не факты — это тревожный фильтр восприятия. Например: «Стало хуже спаться — и уже фантазии о самом плохом».
44	20	5	text	## 🚪 5. Поведение при тревоге\n\nХочется избегать сложных дел, откладывать или перепроверять себя. Иногда наоборот — появляется желание всё контролировать. Человек может искать подтверждение у других, чтобы успокоиться. Это естественная попытка справиться, просто не всегда эффективная. Например: «Проверяете давление пять раз подряд — “точно ли так?”».
45	20	6	text	## ⚡ 6. Почему тревога усиливается при ХБП и на ГД\n\nОрганизм становится чувствительнее к нагрузкам и колебаниям давления. Мозг может принимать эти ощущения за угрозу. Неопределённость лечения добавляет внутреннего напряжения. Это не “вы стали нервными”, это биология. Например: «В день ГД всегда больше внутреннего напряжения — даже если всё идёт по плану».
46	20	7	text	## ⚖️ 7. Когда тревога полезна, а когда — нет\n\nПолезная тревога помогает собраться. Вредная — забирает силы, мешает спать и думать. Если тревога появляется почти каждый день — она перегружает систему. В такие моменты важно вовремя замечать её сигналы. Например: «Перед сном мысли крутятся, как будто мозг не может выключиться».
47	20	8	text	## ⏳ 8. Простой способ заметить тревогу вовремя\n\nОстановитесь на минуту и прислушайтесь к телу. Если дыхание сбивается, мышцы напряжены — тревога включилась. Несколько медленных выдохов помогут снизить уровень напряжения. Наблюдение даёт контроль. Например: «Стоите в очереди в клинике и вдруг чувствуете, что дыхание стало поверхностным».
48	20	9	text	## 🌬️ 9. Как уменьшить тревогу прямо сейчас\n\nЗамедленное дыхание быстро успокаивает нервную систему. Попробуйте: вдох на 4 секунды — выдох на 6 секунд. Через 1–2 минуты тревога уменьшится. Этот метод работает в любой ситуации. Например: «Лежите на ГД, чувствуете внутреннее дрожание — сделали 6 циклов, и тело отпустило».
49	20	10	text	## 🏋️‍♂️ 10. Тревога — это навык, который можно тренировать\n\nМозг запоминает способы реагирования. Если регулярно замечать тревогу и мягко её снижать — реакции становятся спокойнее. Тревога перестаёт управлять поведением. Маленькие шаги — самое важное. Например: «Раньше вспыхивало сразу, а теперь замечаете тревогу раньше и успеваете её остановить».
8	1	8	text	## **🧠 Почему важно учиться справляться со стрессом**\n\nМы не можем полностью убрать стресс из жизни.  \nНо мы можем научиться **замечать его вовремя** и мягко помогать себе.\n\n**Когда мы умеем снижать стресс**:\n\n🧘 Улучшается сон  \n💖 Снижается давление  \n💪 Появляется больше энергии  \n🧠 Яснее становятся мысли\n\nСтресс и тревога — это **две стороны одного состояния**.  \nСтресс — это реакция _тела_, тревога — реакция _психики_.  \nКогда мы заботимся о теле, психика тоже восстанавливается.\n\nКаждый даже небольшой шаг — дыхание, отдых, тёплый разговор —  \nэто вклад в ваше здоровье, настроение и устойчивость.\n\nВы уже начали этот путь. И вы точно справитесь 💪.
30	19	1	text	## 😊 Что такое эмоции\n\nЭмоции — это быстрые реакции мозга на события.  \nОни помогают понять, что для нас важно.  \nЭмоции появляются автоматически — мы их не выбираем.  \nНо мы можем выбирать, как на них отвечать.  \n**Например:** «Услышал новость — и внутри сразу отклик, ещё до мыслей».
31	19	2	text	## 🌡 Как эмоции ощущаются в теле\n\nЭмоции всегда проявляются телом: дыхание, сердце, напряжение, тепло.  \nТело реагирует даже раньше, чем мы осознаём, что чувствуем.  \nПоэтому эмоции важнее “чувствовать”, чем угадывать.  \nТело — лучший индикатор.  \n**Например:** «Почувствовал тревогу по сердцебиению, а мыслей ещё не было».
32	19	3	text	## 🧠 Зачем нужны эмоции\n\nЭмоции помогают принимать решения и ориентироваться в жизни.  \nОни подсказывают, что хорошо, а что вызывает опасение.  \nБез эмоций человек был бы как выключенный навигатор.  \nЭмоции — часть нормальной защиты организма.  \n**Например:** «Разозлился — значит что-то нарушило мои границы».
33	19	4	text	## 🎭 Все эмоции нормальны\n\nНе бывает “плохих” эмоций — каждая выполняет свою задачу.  \nСтрах защищает, злость помогает отстаивать себя, грусть даёт время восстановиться.  \nПроблемы возникают не от эмоций, а от того, как мы на них реагируем.  \nРазрешить себе чувствовать — уже облегчение.  \n**Например:** «Погрустил немного — и стало легче дышать».
34	19	5	text	## 😵 Почему эмоции усиливаются при ХБП\n\nКогда тело устаёт, эмоции становятся ярче.  \nНедостаток энергии, токсины в крови и тревога усиливают чувствительность.  \nИз-за этого реакции могут быть резче обычного.  \nЭто биология, а не “характер испортился”.  \n**Например:** «Раньше спокойно относился, а теперь мелочь выводит из равновесия».
35	19	6	text	## 🔍 Как распознать эмоцию\n\nЛучший способ — остановиться на секунду и спросить: “Что я сейчас чувствую?”  \nЕсли трудно назвать — опирайтесь на тело.  \nТепло, сжатие, дрожь, тяжесть — это язык эмоций.  \nНазвание приходит позже.  \n**Например:** «В груди стало тесно — значит, тревога».
36	19	7	text	## 🧩 Эмоции ≠ мысли\n\nМысли — это объяснения, а эмоции — реакции.  \nИногда мысли усиливают эмоцию, иногда наоборот.  \nЕсли разделить одно от другого, становится легче управлять состоянием.  \nСначала эмоция, потом мысль — такой порядок.  \n**Например:** «Сначала вспыхнуло раздражение, а потом придумал объяснение».
37	19	8	text	## 🧘 Что помогает пережить сильную эмоцию\n\nДышать медленнее, переключиться на тело, замедлить движения.  \nЭти простые действия снижают накал реакции.  \nЭмоция сама по себе длится недолго — 60–90 секунд.  \nЕсли не подливать мысли, она проходит мягче.  \n**Например:** «Сделал три медленных выдоха — и злость отпустила».
38	19	9	text	## 🤝 Эмоции легче переносить с поддержкой\n\nКогда рядом есть человек, который слушает без давления, эмоции проходят быстрее.  \nПоддержка снижает напряжение нервной системы.  \nНе надо объяснять всё подробно — важно просто быть услышанным.  \nРазделённая эмоция — уже наполовину прожитая.  \n**Например:** «Сказал “мне тяжело” — и внутри стало спокойнее».
69	23	1	text	## 🌟 Что такое мотивация?\nМотивация — это энергия, которая помогает начинать и продолжать дела. Она появляется, когда есть смысл и цель. Но она может пропадать из-за усталости, болезни или эмоционального напряжения. Это нормальные колебания, а не “характер”. Например: «Сегодня всё получается, а завтра — сил нет даже на мелочи».
70	23	2	text	## ⚙️ Как мотивация работает в норме\nВ здоровом теле мозг легко включает “режим действия”. Происходит так: появился импульс → сделали → почувствовали результат → захотелось продолжать. Этот цикл поддерживает ощущение “я справляюсь”. Когда система не нарушена, дела даются легче. Например: «Сделал маленькое дело — и как будто зарядился».
71	23	3	text	## 📉 Почему при ХБП мотивация часто падает\nПри ХБП в крови могут накапливаться токсины — они вызывают усталость и спутанность. Пониженный уровень красных кровяных клеток снижает энергию. После ГД силы у многих восстанавливаются медленно. То, что раньше было “легко”, может требовать усилий. Например: «Хочу заняться делами, но тело как будто выключено».
72	23	4	text	## 😟 Эмоции сильно влияют на мотивацию\nКогда настроение падает, мотивация уходит вместе с ним. Тревога, переживания и неопределённость съедают энергию. Если мозг занят плохими мыслями, на активность остаётся мало сил. Поэтому для мотивации важно снизить внутреннее напряжение. Например: «Хочешь делать, но в голове крутится беспокойство — и руки опускаются».
73	23	5	text	## 🚫 Почему “заставить себя” не работает\nЧем сильнее давление, тем больше сопротивление. Мозг воспринимает принуждение как угрозу и тормозит действия. Из-за этого иногда получается наоборот: чем больше “надо”, тем меньше сил. Подход “через усилие” редко срабатывает при хронической усталости. Например: «Говоришь себе “соберись”, а становится только тяжелее».
74	23	6	text	## 🐾 Маленькие шаги — лучший вариант\nБольшие задачи пугают и вызывают сопротивление. Если разбить дело на маленькие кусочки, оно становится выполнимым. Каждый маленький шаг даёт ощущение успеха. Так запускается мягкий, безопасный мотивационный цикл. Например: «Не уборка всей квартиры — а сложить одну стопку вещей».
75	23	7	text	## ⏳ Важна не сила, а регулярность\nДаже 5–10 минут активности дают эффект, если делать их часто. Мозг запоминает повторение и начинает помогать. Так постепенно формируется привычка. Маленькие регулярные действия дают больше, чем редкие “рывки”. Например: «Немного пошевелился каждый день — и через неделю уже легче двигаться».
76	23	8	text	## 🔄 Как вернуть ощущение контроля\nМотивация падает, когда кажется, что ничего не зависит от тебя. Но ощущение контроля можно вернуть маленькими решениями. Задавайте вопрос: «Что я могу сделать сегодня на 5% лучше?» Даже маленький выбор возвращает стабильность. Например: «Не могу всё изменить, но могу выбрать маленькое действие, которое мне по силам».
77	23	9	text	## 🤝 Поддержка сильно помогает\nКогда рядом есть люди, которые не давят, а просто поддерживают — начинать легче. Иногда достаточно сказать, что трудно. Чувство, что ты не один, снижает напряжение и добавляет сил. Социальная поддержка — мощный источник энергии. Например: «Друг написал “держись”, и что-то внутри стало спокойнее — и силы появились».
78	23	10	text	## 🚀 Мотивация — это не вдохновение, а процесс\nНе всегда нужно ждать “правильного настроения”. Мотивация обычно приходит после действия, а не до него. Главное — сделать маленький шаг, который посильный. Это запускает движение вперёд. Например: «Сначала тяжело начать, а потом все становится проще, чем казалось».
79	24	1	text	## 🧠 Что такое когнитивные способности?\n\nКогнитивные способности — это внимание, память, скорость мышления и способность принимать решения.\nОни помогают нам ориентироваться в жизни и справляться с делами.\nПри усталости и болезни эти функции могут замедляться.\nЭто не “глупею”, а реакция организма на нагрузку.\n**Например:** «Слушаю, а потом понимаю, что не помню половину слов».
80	24	2	text	## ⚡ Как мозг работает в норме\n\nВнимание помогает сосредоточиться, память — сохранить информацию, мышление — связать всё вместе.\nКогда организм отдохнувший и в балансе, мозг работает быстро и чётко.\nДела выполняются автоматически и без напряжения.\nМы легко удерживаем фокус и принимаем решения.\n**Например:** «Раньше задачи на работе решались “на автомате”».
81	24	3	text	##  🩸 Почему при ХБП появляются трудности\n\nКогда в крови накапливаются токсины, мозг работает медленнее.\nЕсли мало красных кровяных клеток — мозгу не хватает энергии.\nПосле ГД возможна слабость и “туман в голове”.\nЭто распространённое и обратимое состояние.\n**Например:** «После диализа хочется просто полежать, а думать тяжело».
82	24	4	text	## 😵 Что ощущает человек\n\nМысли могут становиться медленными или “липкими”.\nТрудно сосредоточиться, удерживать внимание или переключаться.\nИнформация “пролетает” мимо, даже если слушаешь внимательно.\nИногда сложно подобрать слова или вспомнить, что хотел сказать.\n**Например:** «Стою у холодильника и не помню, зачем пришёл».
83	24	5	text	## 🔄 Почему память даёт сбои\n\nПамять страдает, когда мозг перегружен усталостью.\nЕсли сил мало, мозг выбирает только самое важное — остальное “отпускает”.\nПри стрессе и тревоге память ухудшается ещё сильнее.\nЭто не связано с интеллектом.\n**Например:** «Читал инструкцию утром — вечером будто впервые вижу».
84	24	6	text	## 🎯 Что происходит с вниманием\n\nВнимание становится коротким, как будто канал для концентрации сужается.\nСложно удерживать фокус на одном деле.\nЛегко отвлечься на мелочи.\nПосле ГД это особенно заметно.\n**Например:** «Начал смотреть бумагу от врача, а через минуту уже читаю третью строку в третий раз».
85	24	7	text	## 🧩 Как это влияет на повседневность\n\nДела, которые раньше занимали 5 минут, теперь требуют больше времени.\nПоявляется ощущение “я стал медленнее”.\nМожно избегать новых задач из-за опасения ошибиться.\nЭто создаёт замкнутый круг: меньше дел → меньше уверенности → ещё меньше сил.\n**Например:** «Получил сообщение — читаю три раза, чтобы понять».
86	24	8	text	## 🌱 Хорошая новость — мозг можно поддержать\n\nДаже маленькие шаги помогают улучшить работу мозга.\nПолезно давать себе короткие паузы и не перегружаться.\nЧёткий режим, упорядоченность и простые списки снижают нагрузку.\nМозг любит ясность и маленькие задачи.\n**Например:** «Сделал список на день — сразу легче и понятнее».
87	24	9	text	##  🏋️‍♂️ Простые упражнения для мозга\n\nКороткие задания помогают “разогреть” мышление.\nЭто может быть чтение пары абзацев, лёгкая головоломка, просмотр интересного материала.\nВажно делать это без давления — по 5–10 минут.\nРегулярность работает лучше, чем длительность.\n**Например:** «Каждый день решаю маленький пазл — становится легче сосредоточиться».
88	24	10	text	## 🔧 Что делать в моменты “тумана”\n\nНе ругать себя и не пытаться “взять силой”.\nДайте мозгу минуту: медленный вдох, выдох, короткая пауза.\nРазбейте задачу на один маленький шаг.\nКогда туман спадёт — продолжайте постепенно.\n**Например:** «Не могу начать дело — делаю первый шаг: открываю нужный документ и останавливаюсь».
89	25	1	text	## 🔥 Что такое выгорание\n\nВыгорание — это состояние сильного истощения, когда эмоции и силы почти на нуле.  \nЧеловек чувствует, что будто “опустел внутри”.  \nЭто не лень и не слабость, а естественная реакция на длительную нагрузку.  \nОсобенно часто возникает при хронических болезнях.  \n**Например:** «Просыпаешься и сразу чувствуешь усталость, даже если почти ничего не делал».
90	25	2	text	## 🌑 Почему пациенты с ХБП часто сталкиваются с выгоранием\n\nГД забирает много энергии — физически и эмоционально.  \nРежим лечения ограничивает свободу и создаёт ощущение “жизнь по расписанию”.  \nПостоянная усталость мешает восстанавливаться.  \nЭто накапливается и приводит к истощению.  \n**Например:** «Неделя только началась, а ощущение — будто уже конец месяца».
91	25	3	text	## 🩶 Как выгорание ощущается в теле\n\nПоявляется хроническая слабость, тяжесть в теле, сильная усталость после простых действий.  \nМожет быть ощущение “тумана” или замедления.  \nСон хуже восстанавливает.  \nЭто реакция организма на долгий стресс.  \n**Например:** «Сходил в магазин — и нужен час, чтобы прийти в себя».
95	25	7	text	## 🎛 Почему восстановиться сложно\n\nПлохое самочувствие и усталость от ГД забирают силы, которые нужны для восстановления.  \nИз-за этого человек попадает в замкнутый круг: мало энергии → меньше дел → меньше радости → ещё меньше энергии.  \nРазорвать круг можно только маленькими шагами.  \nСразу “собраться” не получится — и это нормально.  \n**Например:** «Хочу начать что-то полезное, но сил нет даже подумать об этом».
96	25	8	text	## 🌱 Как начать выходить из выгорания\n\nВажно снижать давление на себя и давать телу отдохнуть маленькими порциями.  \nПомогают простые, короткие действия: тёплый душ, спокойная музыка, лёгкое движение.  \nДаже 5 минут восстановления — это вклад.  \nМозг постепенно “размораживается”.  \n**Например:** «Посидел спокойно под пледом — и внутри стало чуть теплее».
97	25	9	text	## 🤝 Поддержка — ключевой фактор\n\nРазговор с близким, диалог с врачом или просто добрые слова дают ощущение опоры.  \nКогда человек не один, восстановление идёт быстрее.  \nНе нужно объяснять всё подробно — иногда достаточно сказать: “мне тяжело”.  \nПоддержка снижает давление на нервную систему.  \n**Например:** «Друг спросил, как дела — и напряжение немного отпустило».
98	25	10	text	## 🔧 Как понять, что состояние улучшается\n\nВы замечаете маленькие моменты интереса и спокойствия.  \nСтановится чуть легче начинать дела.  \nУтреннее чувство тяжести уменьшается.  \nНастроение выравнивается.  \n**Например:** «Проснулся и впервые за долгое время почувствовал, что сегодня могу что-то сделать».
99	26	1	text	## 🌱 Что такое адаптация\n\nАдаптация — это процесс, в котором человек учится жить с новым состоянием тела.  \nОна не происходит за один день — это путь, в котором есть и подъёмы, и откаты.  \nСо временем мозг и эмоции находят новый баланс.  \nАдаптация — не “смириться”, а научиться жить по-новому.  \n**Например:** «Сначала всё пугало, а потом стало понятнее, как день устроить».
100	26	2	text	## 🧭 Почему адаптация важна\n\nКогда человек понимает, что с ним происходит, тревоги становится меньше.  \nПоявляется ощущение контроля и предсказуемости.  \nЭто снижает стресс и помогает телу работать спокойнее.  \nАдаптация делает жизнь стабильнее даже при сложных обстоятельствах.  \n**Например:** «Когда понял свой режим, дни перестали казаться хаосом».
101	26	3	text	## 🌊 Почему в начале трудно\n\nПри хроническом состоянии происходит много изменений: режим, самочувствие, отношения, планы.  \nМозг не любит резких перемен, поэтому реагирует тревогой и усталостью.  \nЧеловек может ощущать потерю привычной жизни.  \nЭто естественная реакция, а не “слабость”.  \n**Например:** «Оглянулся и понял, что всё стало другим — и это испугало».
102	26	4	text	## 🔄 Этапы адаптации\n\nСначала бывает шок или отрицание.  \nПотом появляется злость, страх или раздражение.  \nПозже — поиск новых опор и способов жить дальше.  \nИ лишь потом приходит спокойное принятие.  \n**Например:** «Сначала думал “этого не может быть”, а потом начал искать, как жить с этим».
103	26	5	text	## 🧠 Как меняется мышление\n\nСо временем человек начинает лучше понимать свои ограничения и возможности.  \nМозг перестраивает привычки и создаёт новые “автоматические” решения.  \nТо, что раньше казалось страшным, становится рутиной.  \nПоявляется уверенность в собственных силах.  \n**Например:** «Раньше боялся процедур, а теперь знаю, что делать в любой ситуации».
104	26	6	text	## ⚖ Новые границы возможностей\n\nПри хроническом заболевании силы распределяются по-другому.  \nВажно не пытаться жить “как раньше”, а искать свой новый темп.  \nГраницы можно расширять постепенно, без рывков.  \nНебольшие успехи дают много стабильности.  \n**Например:** «Раньше делал всё за день, теперь делю на два — и чувствую себя лучше».
105	26	7	text	## 🤝 Роль окружения\n\nПоддержка близких помогает адаптации идти мягче.  \nВажно, чтобы окружающие не давили и не требовали “быть как раньше”.  \nИногда нужна не помощь, а просто понимание и спокойствие.  \nАдаптация — совместный процесс.  \n**Например:** «Сказали: “делай в своём темпе” — и внутри стало легче».
106	26	8	text	## 🧘 Эмоциональная часть адаптации\n\nПри хронических состояниях эмоции усиливаются: тревога, грусть, раздражение.  \nНо именно через эмоции человек учится понимать себя заново.  \nПозволить себе чувствовать — это шаг к устойчивости.  \nЭмоции со временем становятся тише и понятнее.  \n**Например:** «Раньше злость захлёстывала, теперь понимаю, что это просто усталость».
107	26	9	text	## 🔧 Маленькие шаги помогают больше всего\n\nАдаптация строится на ежедневных маленьких действиях.  \nЧёткий режим, короткие перерывы, небольшие задачи создают опору.  \nТак тело и мозг понимают новую систему жизни.  \nМаленькие шаги формируют чувство безопасности.  \n**Например:** «Добавил один маленький ритуал — и день стал спокойнее».
108	26	10	text	## 🌤 Как понять, что адаптация наступила\n\nСтановится меньше страха и больше ясности.  \nЧеловек знает, что помогает, а что — наоборот.  \nПоявляется ощущение, что жизнь снова поддаётся управлению.  \nПланы становятся реальнее, а дни — предсказуемее.  \n**Например:** «Проснулся и поймал себя на мысли, что больше не боюсь завтрашнего дня».
1	1	1	text	## **🧠 Что такое стресс?**\n\n**Стресс** — это естественная реакция нашего организма на трудности, перемены или нагрузку. Он включает в себя физические и эмоциональные проявления.\nКогда мы переживаем стресс, тело напрягается: учащается пульс, дыхание становится поверхностным, мышцы напряжены. Это древний способ выживания — «бей или беги».\nНемного стресса может быть даже полезно: он помогает сосредоточиться, собраться. Но если стресс длится долго и не проходит — он начинает вредить.\nНа диализе стресс возникает часто: из-за процедур, ограничений, боли или чувства неопределённости. Это нормально.\nВажно не игнорировать стресс, а учиться замечать его и мягко помогать себе.
2	1	2	text	## **🧠 Виды стресса**\n\nСтресс — не всегда плохо❗\n\n**Эустресс** — это "полезный" стресс. Он даёт энергию и мотивацию: мы мобилизуемся, собираемся, решаем задачу. Например, перед важным делом. Он проходит — и мы восстанавливаемся.\n\n**Дистресс** — вредный стресс. Он возникает, когда нагрузка сильная или длительная, и организм не успевает восстановиться.\n\nВ результате мы чувствуем себя измотанными, тревожными, раздражительными.\n\n❗ **Последствия дистресса**:\n• Постоянная усталость  \n• Проблемы со сном  \n• Повышение давления  \n• Ухудшение памяти и внимания  \n• Повышенный риск осложнений при ХБП\n\nПоэтому важно замечать стресс и вовремя помогать себе.
3	1	3	text	## **🧠 Как стресс проявляется в теле**\n\nСтресс — это не только про мысли. Он ощущается через тело.\nКогда мы в напряжении, организм включает режим "тревоги".  \n\n**Появляются телесные признаки**:\n• ❤️ Учащённое сердцебиение  \n• 😤 Быстрое, поверхностное дыхание  \n• 💦 Потливость, дрожь  \n• 💢 Напряжение в мышцах  \n• 🌀 Неусидчивость или желание «замереть»\n\nЭти реакции — не слабость, а защитная система организма.  \nНо если они появляются часто и мешают жить — это сигнал, что тело нуждается в заботе.\n\nПациентам на диализе особенно важно уметь замечать такие сигналы.  \nТак мы учимся распознавать стресс до того, как он накапливается.
4	1	4	text	## **🧠 Стресс и хроническая болезнь**\n\nЖизнь с хронической болезнью и диализом — это постоянная нагрузка.  \nСтресс становится частью повседневности, даже если мы не всегда это замечаем.\n\n📌 **Что может вызывать стресс у пациента на ГД**:\n• 💉 Регулярные процедуры  \n• 🚫 Ограничения в питании и жидкости  \n• ❓ Неопределённость будущего  \n• 💬 Переживания за здоровье и близких  \n• 🛌 Физическая слабость, усталость\n\nЭти факторы могут усиливать тревожность, нарушать сон и снижать мотивацию к лечению.\n\nВажно помнить: стресс в такой ситуации — это **не слабость**, а **нормальная реакция организма**.\n\nНо мы можем научиться помогать себе — шаг за шагом снижать внутреннее напряжение и восстанавливаться.
\.


--
-- TOC entry 5113 (class 0 OID 18579)
-- Dependencies: 240
-- Data for Name: lesson_progress; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.lesson_progress (id, patient_token, lesson_id, last_card_index, is_completed, updated_at) FROM stdin;
1	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	0	t	2025-12-05 13:10:43.908286+03
2	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	21	0	t	2025-12-05 20:44:51.624225+03
3	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	22	0	t	2025-12-06 09:50:26.002433+03
4	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	20	0	t	2025-12-06 12:22:06.423731+03
5	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	19	0	t	2025-12-07 19:31:09.295778+03
6	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	23	0	f	2025-12-08 11:41:13.357605+03
7	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	24	0	f	2025-12-22 22:41:10.747257+03
\.


--
-- TOC entry 5119 (class 0 OID 18637)
-- Dependencies: 246
-- Data for Name: lesson_test_questions; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.lesson_test_questions (id, test_id, order_index, question_text, option_1, option_2, option_3, option_4, correct_option, is_active) FROM stdin;
1	21	1	Что происходит с телом во время стрессовой реакции?	Снижается аппетит	Замедляется пульс	Появляется сонливость	Учащается сердцебиение и дыхание	4	t
2	21	2	Какой стресс помогает адаптироваться к изменениям?	Дистресс	Эустресс	Хронический стресс	Стресс от усталости	2	t
3	21	3	Что может быть ранним признаком стресса?	Раздражительность и напряжение	Сильное чувство радости	Улучшение сна	Повышение энергии	1	t
4	21	4	Как мозг реагирует на стресс?	Замедляет реакции	Тормозит внимание	Переходит в режим «бей или беги»	Снижает приток крови к мышцам	3	t
5	21	5	Какой из вариантов помогает заметить стресс?	Игнорирование усталости	Отслеживание дыхания и напряжения в теле	Постоянная занятость	Резкое повышение нагрузки	2	t
6	21	6	Что происходит при длительном стрессе?	Организм легко восстанавливается	Улучшается иммунитет	Повышается риск истощения и ухудшения самочувствия	Тело становится более энергичным	3	t
7	21	7	Какой способ может снизить уровень стресса?	Быстрое поверхностное дыхание	Изоляция от окружающих	Замедление дыхания и расслабление мышц	Постоянный анализ проблемы	3	t
8	21	8	Как стресс влияет на сон?	Делает сон более глубоким	Может ухудшать засыпание и качество сна	Не влияет на сон	Всегда вызывает сонливость	2	t
9	21	9	Как стресс влияет на внимание?	Повышает концентрацию надолго	Не оказывает никакого влияния	Может ухудшать внимание и усиливать отвлекаемость	Делает человека спокойнее	3	t
10	21	10	Что из перечисленного может быть телесным признаком стресса?	Напряжение мышц	Повышенная энергия	Полное расслабление	Улучшение гибкости мышц	1	t
11	22	1	Что такое эмоции по отношению к событиям в жизни?	Слабость характера	Признак лени	Всегда болезнь психики	Быстрые реакции мозга, помогающие понять, что для нас важно	4	t
12	22	2	Что важно помнить про появление эмоций?	Эмоции появляются автоматически, а мы можем выбирать, как на них реагировать	Эмоции появляются по расписанию	Эмоции есть только у молодых людей	Мы можем полностью их контролировать	1	t
13	22	3	Как чаще всего эмоции проявляются в теле?	Никак, это только мысли	Только через боль в суставах	Через дыхание, сердцебиение, напряжение, тепло или тяжесть в теле	Только через повышение температуры	3	t
14	22	4	Зачем человеку нужны эмоции?	Чтобы мешать принимать решения	Они помогают ориентироваться в жизни и принимать решения, как навигатор	Чтобы скрывать свои потребности	Никакой пользы от эмоций нет	2	t
15	22	5	Какие эмоции считаются нормальными?	Только радость и спокойствие	Только страх и злость	Все эмоции нормальны, у каждой своя задача	Нормальных эмоций не бывает	3	t
16	22	6	Почему при хронической болезни эмоции могут усиливаться?	Потому что человек стал «слишком чувствительным» по характеру	Потому что пациент стал меньше общаться	Это всегда признак психического расстройства	Из-за усталости тела, токсинов в крови и тревоги — мозг реагирует острее	4	t
17	22	7	Как лучше распознать, что именно вы сейчас чувствуете?	Остановиться и обратить внимание на тело: сжатие, тепло, дрожь, тяжесть	Игнорировать ощущения и ждать, пока само пройдёт	Ругать себя за эмоции	Спрашивать только мнение окружающих	1	t
18	22	8	Чем эмоции отличаются от мыслей?	Мысли — это реакции тела, эмоции — только слова	Мысли — это объяснения, а эмоции — быстрые реакции, которые возникают сначала	Эмоции появляются позже, чем мысли	Разницы нет, это одно и то же	2	t
19	22	9	Что помогает пережить сильную эмоцию мягче?	Повышать голос на близких	Запретить себе чувствовать	Дышать медленнее, обратить внимание на тело, немного замедлиться	Подливать мысли: постоянно прокручивать ситуацию в голове	3	t
20	22	10	Почему эмоции легче переносить с поддержкой другого человека?	Потому что кто-то может решить проблему за вас	Потому что эмоции тогда исчезают навсегда	Потому что надо всегда оправдываться перед другими	Потому что поддержка снижает напряжение нервной системы, и разделённая эмоция проживается легче	4	t
21	23	1	Что такое тревога?	Ненужная реакция организма	Признак слабости характера	Сигнал мозга о возможной опасности, даже если угрозы нет	Редкое расстройство психики	3	t
22	23	2	Зачем человеку тревога?	Чтобы мешать спокойно жить	Чтобы помочь замечать возможные риски и быстрее реагировать	Чтобы снижать уровень энергии	Чтобы усиливать стресс	2	t
23	23	3	Как тревога чаще всего ощущается в теле?	Сильное расслабление	Тяжесть в ногах и повышение температуры	Дрожь, сердцебиение, напряжение, одышка	Острая боль в мышцах	3	t
24	23	4	Что происходит в мыслях при тревоге?	Мысли становятся быстрыми и более тревожными	Мысли полностью исчезают	Только улучшается концентрация	Появляется сильная эйфория	1	t
25	23	5	Как тревога влияет на поведение?	Усиливает уверенность	Появляется избегание, перепроверки или стремление всё контролировать	Полностью исчезает внимание	Всегда вызывает агрессию	2	t
26	23	6	Почему тревога может усиливаться при ХБП и на диализе?	Это означает, что человек стал нервным	Из-за чувствительности организма к нагрузкам и перепадам давления мозг чаще воспринимает сигналы как угрозу	Потому что человек недостаточно старается успокоиться	Потому что тревога — обязательная часть лечения	2	t
27	23	7	Когда тревога становится вредной?	Когда появляется редко	Когда появляется почти каждый день, мешает спать и забирает силы	Когда человек устал	Когда уровень сахара в норме	2	t
28	23	8	Как вовремя заметить тревогу?	Игнорировать ощущения	Ждать, пока тревога станет сильнее	Прислушаться к телу: дыхание, напряжение, мышцы	Расспрашивать других, заметили ли они тревогу	3	t
29	23	9	Какое простое упражнение помогает снизить тревогу?	Быстрое дыхание	Вдох на 4 секунды — выдох на 6 секунд	Повышение физической нагрузки	Длительное напряжение мышц	2	t
30	23	10	Почему тревога — это навык, который можно тренировать?	Потому что мозг учится реагировать спокойнее при регулярной практике	Потому что тревога проходит сама	Потому что тревога возникает только у некоторых людей	Потому что тревогу можно выключить как кнопку	1	t
31	24	1	Почему сон так важен для организма?	Он помогает мозгу и телу восстанавливаться	Он увеличивает артериальное давление	Он делает мысли быстрее и тревожнее	Сон нужен только при болезни	1	t
32	24	2	Почему при ХБП сон часто нарушается?	Из-за слишком долгого отдыха	Токсины, стресс, колебания давления и судороги могут мешать заснуть	Потому что человек спит слишком рано	Потому что мозг перестаёт отдыхать	2	t
33	24	3	Что происходит в голове, когда человек испытывает сильную усталость?	Мысли полностью исчезают	Мозг легче переключается на отдых	Мысли крутятся, как будто ум не может «найти паузу»	Появляется постоянная сонливость	3	t
34	24	4	Как выглядит нарушение сна?	Глубокий сон без пробуждений	Человек долго не может заснуть или часто просыпается	Просыпается ровно в одно и то же время	Чувствует себя бодро каждое утро	2	t
35	24	5	Как тело реагирует на плохой сон?	Становится легче концентрироваться	Появляется раздражительность, тревога и упадок сил	Хочется много двигаться	Улучшается память	2	t
36	24	6	Что помогает улучшить сон?	Чтение новостей в кровати	Стабильный вечерний ритуал: мягкий свет, спокойная музыка, тёплый душ	Яркое освещение перед сном	Просмотр сериалов до момента засыпания	2	t
37	24	7	Почему режим сна так важен?	Потому что организм любит предсказуемость и биоритмы стабилизируются	Потому что сон становится короче	Потому что легче просыпаться ночью	Потому что режим увеличивает потребность в кофеине	1	t
38	24	8	Как успокоить мозг перед сном?	Активно обсуждать сложные темы	Делать длинный вдох и короткий выдох	Медленное дыхание с длинным выдохом помогает снизить напряжение	Вспоминать все нерешённые задачи	3	t
39	24	9	Что чаще всего мешает заснуть?	Тёплая комната	Слабая освещённость	Поздняя активность, яркие экраны и напряжённые разговоры	Тихая музыка	3	t
40	24	10	Как понять, что сон стал лучше?	Становится легче засыпать, появляется больше энергии утром	Увеличивается количество ночных пробуждений	Появляется желание ложиться позже	Память ухудшается	1	t
41	25	1	Что такое копинг?	Способ избежать любых эмоций	Метод контроля артериального давления	Способы, которыми человек справляется со стрессом	Признак слабого характера	3	t
42	25	2	Что важно помнить о копинг-стратегиях?	Они формируются только во взрослом возрасте	Они бывают только правильные и неправильные	Они разные, и каждая может помогать или мешать в зависимости от ситуации	Их нельзя менять	3	t
43	25	3	Что относится к проблемно-ориентированному копингу?	Попытка решить проблему, спланировать действия, получить информацию	Попытка скрыть эмоции	Избегание любых решений	Примеривание расслабляющих техник	1	t
44	25	4	Когда проблемно-ориентированный копинг особенно полезен?	Когда ситуацию вообще невозможно изменить	Когда нужно снизить тревогу через дыхание	Когда ситуация изменяема и нужны конкретные шаги	Когда хочется отложить проблему	3	t
45	25	5	Что относится к эмоционально-ориентированному копингу?	Действие по плану	Снижение напряжения через дыхание, разговор или прогулку	Откладывание дел	Катастрофизация ситуации	2	t
46	25	6	Что такое когнитивный копинг?	Игнорирование любых мыслей	Полный контроль над эмоциями	Способ посмотреть на ситуацию под другим углом, переосмыслить её	Уход от общения	3	t
47	25	7	Что характеризует избегающий копинг?	Решение проблемы шаг за шагом	Перепроверка фактов	Откладывание дел, уход в отвлечение, попытка не думать о проблеме	Просьба о помощи	3	t
48	25	8	Что относится к защитному копингу?	Делать вид, что всё в порядке, даже если внутри тяжело	Активно решать проблему	Переосмыслять ситуацию	Просить о поддержке	1	t
49	25	9	Что такое социальный копинг?	Оставаться одному в любой ситуации	Разделять переживания, общаться, просить поддержку	Скрывать эмоции от окружающих	Избегать разговоров	2	t
50	25	10	Как понять, что копинг-стратегия помогает?	Появляется чувство ясности, дыхание становится легче, мысли спокойнее	Настроение резко скачет	Проблемы перестают существовать навсегда	Появляется желание избегать действий	1	t
51	26	1	Что такое мотивация?	Энергия, которая помогает начинать и продолжать дела	Способ избежать обязанностей	Признак сильного характера	Состояние, возникающее только при хорошем настроении	1	t
52	26	2	Как мотивация работает в норме?	Появился импульс → сделали → почувствовали результат → захотелось продолжать	Мотивация возникает только после отдыха	Действия происходят автоматически без мыслей	Мозг включает мотивацию только при сильном стрессе	1	t
53	26	3	Почему при ХБП мотивация часто падает?	Потому что человек становится ленивым	Потому что организм боится нагрузки	Из-за токсинов, усталости, снижения энергии и медленного восстановления после ГД	Потому что мотивация исчезает с возрастом	3	t
54	26	4	Как эмоции влияют на мотивацию?	Никак не связаны	Плохое настроение и тревога могут снижать энергию и желание что-либо делать	Всегда усиливают активность	Мотивация не зависит от состояния нервной системы	2	t
55	26	5	Почему «заставить себя» часто не работает?	Потому что человек плохо старается	Чем сильнее давление, тем больше сопротивление — мозг воспринимает это как угрозу	Это работает только при хорошем сне	Заставлять себя — лучший способ вернуть энергию	2	t
56	26	6	Почему маленькие шаги помогают больше, чем большие задачи?	Большие задачи всегда легче	Маленькие шаги создают ощущение успеха и запускают мягкий мотивационный цикл	Маленькие шаги занимают много энергии	Большие задачи быстрее мотивируют	2	t
57	26	7	Почему важна регулярность?	Потому что организм не любит повторы	Потому что даже 5–10 минут активности ежедневно формируют привычку и поддерживают энергию	Потому что редкие рывки дают больше эффекта	Регулярность важна только в спорте	2	t
58	26	8	Как можно вернуть ощущение контроля?	Пытаться изменить всё сразу	Делать только большие шаги	Выбирать маленькие действия и спрашивать себя: «Что я могу сделать на 5% лучше?»	Откладывать задачи на потом	3	t
59	26	9	Как социальная поддержка влияет на мотивацию?	Мешает, потому что отвлекает	Усиливает напряжение	Помогает снижать стресс и делает начало действий легче	Не влияет	3	t
78	28	8	Что помогает начать выходить из выгорания?	Сильное давление на себя	Игнорирование усталости	Маленькие шаги, мягкий отдых, короткие действия, снижающие напряжение	Резкое увеличение нагрузки	3	t
60	26	10	Почему мотивация — это процесс?	Потому что она появляется только при вдохновении	Мотивация обычно приходит после действия — достаточно начать с маленького шага	Потому что она работает сама по себе	Потому что её можно включить по команде	2	t
61	27	1	Что включают в себя когнитивные способности?	Только память	Только скорость речи	Внимание, память, скорость мышления и принятие решений	Только способность запоминать цифры	3	t
62	27	2	Почему когнитивные функции могут ухудшаться при ХБП?	Из-за накопления токсинов и снижения энергии при анемии	Потому что человек меньше читает	Потому что мозг перестаёт работать	Это неизбежный признак старения	1	t
63	27	3	Что человек может ощущать при снижении когнитивных функций?	Мысли становятся быстрыми и резкими	Мысли могут быть медленными, липкими, трудно сосредоточиться	Память полностью исчезает	Появляется вдохновение	2	t
64	27	4	Почему память даёт сбои при усталости и стрессе?	Потому что мозг выбирает только самое важное, остальное отпускает	Потому что человек стал меньше стараться	Потому что память работает лучше ночью	Потому что мозг перестаёт воспринимать информацию	1	t
65	27	5	Что происходит с вниманием при когнитивной перегрузке?	Оно становится коротким и легко отвлекается	Оно становится сверхустойчивым	Оно полностью отключается	Оно становится идеальным	1	t
66	27	6	Как когнитивные трудности влияют на повседневную жизнь?	Усложняют задачи, требуют больше времени и снижают уверенность	Улучшают способность к многозадачности	Не влияют на выполнение дел	Делают человека бодрее	1	t
67	27	7	Что помогает поддержать работу мозга?	Перегружать себя большими задачами	Короткие паузы, порядок и маленькие задачи	Отказ от отдыха	Игнорирование усталости	2	t
68	27	8	Какие упражнения помогают «разогреть» мозг?	Только силовые тренировки	Только длительные нагрузки более часа	Короткие задания: чтение, лёгкие головоломки, короткие материалы	Отдых без деятельности	3	t
69	27	9	Что делать во время «тумана в голове»?	Ругать себя и усиливать давление	Дать мозгу минуту: вдох-выдох, пауза, один маленький шаг	Продолжать работать без остановки	Ждать, пока всё пройдёт самостоятельно	2	t
70	27	10	Почему когнитивные трудности при ХБП — не признак «глупости»?	Потому что они связаны с нагрузкой на организм, усталостью и биологическими процессами	Потому что мозг меняет структуру	Потому что человек слишком много спит	Потому что это всегда временно и без причин	1	t
71	28	1	Что такое эмоциональное выгорание?	Лень и потеря интереса	Признак слабого характера	Состояние сильного истощения и внутренней пустоты при длительной нагрузке	Обычная усталость после рабочего дня	3	t
72	28	2	Почему пациенты с ХБП чаще сталкиваются с выгоранием?	Потому что они слишком эмоциональны	ГД забирает много энергии, ограничивает свободу и создаёт хроническую усталость	Потому что они мало спят	Потому что нагрузки полностью отсутствуют	2	t
73	28	3	Как выгорание ощущается в теле?	Повышенная бодрость	Хроническая слабость, тяжесть, быстрая утомляемость	Сильное желание заниматься спортом	Безграничная энергия	2	t
74	28	4	Что происходит с эмоциями при выгорании?	Эмоции становятся слабее или резко вспыхивают, появляется раздражительность или пустота	Все эмоции усиливаются и становятся ярче	Эмоции полностью исчезают навсегда	Человек становится исключительно радостным	1	t
75	28	5	Как меняется мышление при выгорании?	Становится легче принимать решения	Мысли становятся тяжёлыми, появляется ощущение безысходности	Ускоряется скорость восприятия	Улучшается способность к планированию	2	t
76	28	6	Что происходит с интересами?	Появляются новые увлечения	Интересы становятся ярче	То, что раньше радовало, становится безразличным	Человек резко расширяет круг занятий	3	t
77	28	7	Почему восстановиться от выгорания сложно?	Потому что у человека слишком много энергии	Потому что низкая энергия мешает восстанавливаться, формируется замкнутый круг	Потому что человек слишком много отдыхает	Восстановление всегда происходит автоматически	2	t
79	28	9	Почему поддержка важна при выгорании?	Потому что поддержка снижает напряжение и помогает восстановлению	Потому что без неё восстановление невозможно	Потому что она полностью решает проблему	Поддержка увеличивает нагрузку	1	t
80	28	10	Как понять, что состояние начинает улучшаться?	Появляется больше энергии и сразу хочется больших задач	Настроение резко скачет	Появляются маленькие моменты интереса, спокойствия, становится легче начинать дела	Состояние остаётся прежним, но человек привыкает	3	t
81	29	1	Что такое адаптация при хронической болезни?	Смириться и перестать что-либо менять	Полностью отказаться от прежней жизни	Процесс, в котором человек учится жить с новым состоянием тела и находит новый баланс	Быстрое восстановление сил	3	t
82	29	2	Почему адаптация снижает тревогу?	Потому что человек перестаёт думать о болезни	Потому что понимание происходящего даёт ощущение контроля и предсказуемости	Потому что болезнь проходит быстрее	Потому что человек начинает избегать информации	2	t
83	29	3	Почему в начале адаптации может быть трудно?	Потому что человек не хочет выздоравливать	Из-за множества изменений: режим, самочувствие, планы, отношения	Потому что тело перестаёт реагировать на лечение	Потому что нужно следовать строгой диете	2	t
84	29	4	Какие этапы адаптации описаны в уроке?	Сначала спокойствие, затем принятие, потом тревога	Отрицание → злость/страх → поиск опор → спокойное принятие	Сначала радость, потом отказ от лечения	Этапы отсутствуют — адаптация хаотична	2	t
85	29	5	Как меняется мышление в процессе адаптации?	Появляется больше страхов	Мозг перестаёт воспринимать новые задачи	Возникает понимание своих возможностей, формируются новые привычки, появляется уверенность	Мысли становятся хаотичными навсегда	3	t
86	29	6	Что означает «новые границы возможностей»?	Полное ограничение активности	Поиск нового темпа и постепенное расширение возможностей без рывков	Возврат к нагрузкам как до болезни	Отказ от любых изменений	2	t
87	29	7	Какую роль играет окружение?	Должно требовать прежней активности от человека	Должно подталкивать к большему усилию	Поддержка и принятие окружающих помогают адаптации идти мягче	Окружение не играет роли	3	t
88	29	8	Зачем в адаптации важна эмоциональная работа?	Чтобы подавлять эмоции	Чтобы усилить тревогу и оставаться в напряжении	Через эмоции человек лучше понимает себя и становится устойчивее	Эмоции не связаны с адаптацией	3	t
89	29	9	Почему маленькие шаги особенно эффективны при адаптации?	Потому что большие шаги всегда вредят	Потому что маленькие действия помогают мозгу создать новую систему жизни и дают ощущение безопасности	Потому что маленькие шаги занимают мало времени	Потому что так проще скрыть эмоции	2	t
90	29	10	Как понять, что адаптация наступила?	Человек перестаёт думать о лечении	Появляется хаос и отсутствие режима	Становится меньше страха, больше ясности и ощущение, что жизнь снова управляемая	Полностью исчезают все симптомы	3	t
\.


--
-- TOC entry 5115 (class 0 OID 18597)
-- Dependencies: 242
-- Data for Name: lesson_test_results; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.lesson_test_results (id, test_id, patient_token, score, max_score, passed, answers_json, created_at) FROM stdin;
1	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	5	10	f	[{"is_correct": false, "question_id": 1, "chosen_option": 1, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 3, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 3, "correct_option": 1}, {"is_correct": true, "question_id": 4, "chosen_option": 3, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": true, "question_id": 6, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 7, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 8, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 9, "chosen_option": 3, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 2, "correct_option": 1}]	2025-12-05 12:51:20.768892+03
2	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	4	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": true, "question_id": 6, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 7, "chosen_option": 3, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 3, "correct_option": 2}, {"is_correct": true, "question_id": 9, "chosen_option": 3, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 12:58:04.103956+03
3	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 12:58:24.281809+03
4	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	10	10	t	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": true, "question_id": 2, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 3, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 4, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 5, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 6, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 7, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 8, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 9, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 10, "chosen_option": 1, "correct_option": 1}]	2025-12-05 13:10:43.888867+03
5	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	2	10	f	[{"is_correct": false, "question_id": 1, "chosen_option": 3, "correct_option": 4}, {"is_correct": true, "question_id": 2, "chosen_option": 2, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 2, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": true, "question_id": 9, "chosen_option": 3, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 13:22:33.471902+03
6	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	10	10	t	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": true, "question_id": 2, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 3, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 4, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 5, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 6, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 7, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 8, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 9, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 10, "chosen_option": 1, "correct_option": 1}]	2025-12-05 13:30:38.280823+03
7	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 13:31:49.358036+03
8	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 13:33:31.369019+03
9	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	2	10	f	[{"is_correct": false, "question_id": 1, "chosen_option": 3, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 2, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 2, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 1, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 2, "correct_option": 3}, {"is_correct": true, "question_id": 7, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 8, "chosen_option": 2, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 1, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 3, "correct_option": 1}]	2025-12-05 17:20:55.456826+03
10	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	10	10	t	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": true, "question_id": 2, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 3, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 4, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 5, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 6, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 7, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 8, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 9, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 10, "chosen_option": 1, "correct_option": 1}]	2025-12-05 20:18:25.926136+03
11	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 20:19:55.62116+03
12	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 20:20:14.117209+03
13	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 20:28:38.637431+03
14	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-05 20:35:59.903153+03
15	24	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	0	10	f	[{"is_correct": false, "question_id": 31, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 32, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 33, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 34, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 35, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 36, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 37, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 38, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 39, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 40, "chosen_option": 4, "correct_option": 1}]	2025-12-05 20:43:55.975259+03
16	24	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	10	10	t	[{"is_correct": true, "question_id": 31, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 32, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 33, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 34, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 35, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 36, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 37, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 38, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 39, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 40, "chosen_option": 1, "correct_option": 1}]	2025-12-05 20:44:51.62102+03
17	27	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	0	10	f	[{"is_correct": false, "question_id": 61, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 62, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 63, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 64, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 65, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 66, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 67, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 68, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 69, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 70, "chosen_option": 4, "correct_option": 1}]	2025-12-06 09:10:48.219609+03
18	25	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	10	10	t	[{"is_correct": true, "question_id": 41, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 42, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 43, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 44, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 45, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 46, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 47, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 48, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 49, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 50, "chosen_option": 1, "correct_option": 1}]	2025-12-06 09:50:25.998431+03
19	23	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	0	10	f	[{"is_correct": false, "question_id": 21, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 22, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 23, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 24, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 25, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 26, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 27, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 28, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 29, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 30, "chosen_option": 4, "correct_option": 1}]	2025-12-06 12:11:18.647291+03
20	23	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	10	10	t	[{"is_correct": true, "question_id": 21, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 22, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 23, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 24, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 25, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 26, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 27, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 28, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 29, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 30, "chosen_option": 1, "correct_option": 1}]	2025-12-06 12:22:06.417319+03
21	22	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	10	10	t	[{"is_correct": true, "question_id": 11, "chosen_option": 4, "correct_option": 4}, {"is_correct": true, "question_id": 12, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 13, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 14, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 15, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 16, "chosen_option": 4, "correct_option": 4}, {"is_correct": true, "question_id": 17, "chosen_option": 1, "correct_option": 1}, {"is_correct": true, "question_id": 18, "chosen_option": 2, "correct_option": 2}, {"is_correct": true, "question_id": 19, "chosen_option": 3, "correct_option": 3}, {"is_correct": true, "question_id": 20, "chosen_option": 4, "correct_option": 4}]	2025-12-07 19:31:09.282661+03
22	27	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 61, "chosen_option": 3, "correct_option": 3}, {"is_correct": false, "question_id": 62, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 63, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 64, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 65, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 66, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 67, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 68, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 69, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 70, "chosen_option": 4, "correct_option": 1}]	2025-12-22 22:41:23.994517+03
23	21	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt	1	10	f	[{"is_correct": true, "question_id": 1, "chosen_option": 4, "correct_option": 4}, {"is_correct": false, "question_id": 2, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 3, "chosen_option": 4, "correct_option": 1}, {"is_correct": false, "question_id": 4, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 5, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 6, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 7, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 8, "chosen_option": 4, "correct_option": 2}, {"is_correct": false, "question_id": 9, "chosen_option": 4, "correct_option": 3}, {"is_correct": false, "question_id": 10, "chosen_option": 4, "correct_option": 1}]	2025-12-22 22:50:29.111457+03
\.


--
-- TOC entry 5117 (class 0 OID 18617)
-- Dependencies: 244
-- Data for Name: lesson_tests; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.lesson_tests (id, lesson_id, code, title, short_description, order_index, is_active, created_at, updated_at) FROM stdin;
21	1	01_stress-test	Стресс-тест	\N	1	t	2025-12-05 12:41:51.635785+03	2025-12-05 12:41:51.635785+03
22	19	02_emocii-test	Эмоции-тест	\N	1	t	2025-12-05 12:41:51.661137+03	2025-12-05 12:41:51.661137+03
23	20	03_trevoga-test	Тревога-тест	\N	1	t	2025-12-05 12:41:51.671742+03	2025-12-05 12:41:51.671742+03
24	21	04_son-test	Сон-тест	\N	1	t	2025-12-05 12:41:51.68434+03	2025-12-05 12:41:51.68434+03
25	22	05_koping-strategii-test	Копинг-стратегии-тест	\N	1	t	2025-12-05 12:41:51.696898+03	2025-12-05 12:41:51.696898+03
26	23	06_motivaciya-test	Мотивация-тест	\N	1	t	2025-12-05 12:41:51.707759+03	2025-12-05 12:41:51.707759+03
27	24	07_kognitivka-test	Когнитивка-тест	\N	1	t	2025-12-05 12:41:51.719308+03	2025-12-05 12:41:51.719308+03
28	25	08_emocionalnoe-vygoranie-test	Эмоциональное-выгорание-тест	\N	1	t	2025-12-05 12:41:51.729307+03	2025-12-05 12:41:51.729307+03
29	26	09_adptaciya-k-hroni-test	Адптация_к_хрони-тест	\N	1	t	2025-12-05 12:41:51.741648+03	2025-12-05 12:41:51.741648+03
\.


--
-- TOC entry 5105 (class 0 OID 18431)
-- Dependencies: 232
-- Data for Name: lessons; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.lessons (id, code, topic, title, short_description, order_index, is_active, created_at, updated_at) FROM stdin;
19	02_emocii	Ментальное здоровье	🎭 Эмоции	\N	2	t	2025-12-01 19:47:58.105336+03	2025-12-01 19:47:58.105336+03
20	03_trevoga	Ментальное здоровье	😟 Тревога	\N	3	t	2025-12-01 19:48:15.396321+03	2025-12-01 19:48:15.396321+03
21	04_son	Ментальное здоровье	🛌 Сон	\N	4	t	2025-12-01 19:48:15.408031+03	2025-12-01 19:48:15.408031+03
22	05_koping-strategii	Ментальное здоровье	🔑 Копинг стратегии	\N	5	t	2025-12-01 19:48:15.412288+03	2025-12-01 19:48:15.412288+03
23	06_motivaciya	Ментальное здоровье	💪 Мотивация	\N	6	t	2025-12-01 19:48:15.41769+03	2025-12-01 19:48:15.41769+03
24	07_kognitivnye-sposobnosti	Ментальное здоровье	🧠 Когнитивные способности	\N	7	t	2025-12-01 19:48:15.42223+03	2025-12-01 19:48:15.42223+03
25	08_emocionalnoe-vygoranie	Ментальное здоровье	🔥Эмоциональное выгорание	\N	8	t	2025-12-01 19:48:15.425711+03	2025-12-01 19:48:15.425711+03
26	09_adaptaciya-k-bolezni	Ментальное здоровье	🌼Адаптация к болезни	\N	9	t	2025-12-01 19:48:15.431777+03	2025-12-01 19:48:15.431777+03
1	01_stress	Ментальное здоровье	🤯 Стресс	Короткие карточки	1	t	2025-12-01 12:00:17.701377+03	2025-12-01 12:00:17.701377+03
\.


--
-- TOC entry 5111 (class 0 OID 18554)
-- Dependencies: 238
-- Data for Name: practice_logs; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.practice_logs (id, user_id, practice_id, performed_at, success, effect_rating, comment) FROM stdin;
\.


--
-- TOC entry 5109 (class 0 OID 18537)
-- Dependencies: 236
-- Data for Name: practices; Type: TABLE DATA; Schema: education; Owner: postgres
--

COPY education.practices (id, lesson_id, title, description_md, order_index, is_active) FROM stdin;
\.


--
-- TOC entry 5094 (class 0 OID 18333)
-- Dependencies: 221
-- Data for Name: alembic_version; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.alembic_version (version_num) FROM stdin;
d2ca01903a4c
\.


--
-- TOC entry 5100 (class 0 OID 18365)
-- Dependencies: 227
-- Data for Name: drafts; Type: TABLE DATA; Schema: scales; Owner: postgres
--

COPY scales.drafts (id, user_id, scale_code, current_index, answers, started_at, updated_at) FROM stdin;
\.


--
-- TOC entry 5098 (class 0 OID 18351)
-- Dependencies: 225
-- Data for Name: responses; Type: TABLE DATA; Schema: scales; Owner: postgres
--

COPY scales.responses (id, user_id, scale_code, version, started_at, completed_at, raw_answers, result, interpretation) FROM stdin;
1	1	HADS	1.0	2025-11-26 12:24:27.621707	2025-11-26 12:24:27.620519	{"q1": 3, "q2": 0, "q3": 0, "q4": 3, "q5": 3, "q6": 0, "q7": 3, "q8": 3, "q9": 0, "q10": 3, "q11": 0, "q12": 0, "q13": 3, "q14": 0}	{"A": 15, "D": 6}	A: Выраженная, D: Норма
\.


--
-- TOC entry 5120 (class 0 OID 18663)
-- Dependencies: 247
-- Data for Name: scale_results; Type: TABLE DATA; Schema: scales; Owner: postgres
--

COPY scales.scale_results (id, user_id, scale_code, scale_version, measured_at, result_json, answers_json, created_at, updated_at) FROM stdin;
357373ef-27b7-40b6-9ab1-04f8c9139c7a	1	HADS	1.0	2025-12-07 13:26:33.901386+03	{"ANX": {"score": 21, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 21, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}}	[{"question_id": "A1", "option_id": "A1_1", "score_value": 3}, {"question_id": "D1", "option_id": "D1_4", "score_value": 3}, {"question_id": "A2", "option_id": "A2_1", "score_value": 3}, {"question_id": "D2", "option_id": "D2_4", "score_value": 3}, {"question_id": "A3", "option_id": "A3_1", "score_value": 3}, {"question_id": "D3", "option_id": "D3_4", "score_value": 3}, {"question_id": "A4", "option_id": "A4_1", "score_value": 3}, {"question_id": "D4", "option_id": "D4_1", "score_value": 3}, {"question_id": "A5", "option_id": "A5_1", "score_value": 3}, {"question_id": "D5", "option_id": "D5_1", "score_value": 3}, {"question_id": "A6", "option_id": "A6_1", "score_value": 3}, {"question_id": "D6", "option_id": "D6_4", "score_value": 3}, {"question_id": "A7", "option_id": "A7_1", "score_value": 3}, {"question_id": "D7", "option_id": "D7_4", "score_value": 3}]	2025-12-07 16:26:33.923595+03	2025-12-07 16:26:33.923595+03
99e6f689-b368-4f36-824d-5e1265a3d518	1	HADS	1.0	2025-12-07 13:28:42.681001+03	{"ANX": {"score": 21, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 0, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}}	[{"question_id": "A1", "option_id": "A1_1", "score_value": 3}, {"question_id": "D1", "option_id": "D1_1", "score_value": 0}, {"question_id": "A2", "option_id": "A2_1", "score_value": 3}, {"question_id": "D2", "option_id": "D2_1", "score_value": 0}, {"question_id": "A3", "option_id": "A3_1", "score_value": 3}, {"question_id": "D3", "option_id": "D3_1", "score_value": 0}, {"question_id": "A4", "option_id": "A4_1", "score_value": 3}, {"question_id": "D4", "option_id": "D4_4", "score_value": 0}, {"question_id": "A5", "option_id": "A5_1", "score_value": 3}, {"question_id": "D5", "option_id": "D5_4", "score_value": 0}, {"question_id": "A6", "option_id": "A6_1", "score_value": 3}, {"question_id": "D6", "option_id": "D6_1", "score_value": 0}, {"question_id": "A7", "option_id": "A7_1", "score_value": 3}, {"question_id": "D7", "option_id": "D7_1", "score_value": 0}]	2025-12-07 16:28:42.682181+03	2025-12-07 16:28:42.682181+03
77787db1-f6ce-4e87-92e2-2592a911294b	1	HADS	1.0	2025-12-07 13:32:28.612904+03	{"ANX": {"score": 12, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 11, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}}	[{"question_id": "A1", "option_id": "A1_1", "score_value": 3}, {"question_id": "D1", "option_id": "D1_2", "score_value": 1}, {"question_id": "A2", "option_id": "A2_3", "score_value": 1}, {"question_id": "D2", "option_id": "D2_4", "score_value": 3}, {"question_id": "A3", "option_id": "A3_3", "score_value": 1}, {"question_id": "D3", "option_id": "D3_2", "score_value": 1}, {"question_id": "A4", "option_id": "A4_2", "score_value": 2}, {"question_id": "D4", "option_id": "D4_1", "score_value": 3}, {"question_id": "A5", "option_id": "A5_2", "score_value": 2}, {"question_id": "D5", "option_id": "D5_3", "score_value": 1}, {"question_id": "A6", "option_id": "A6_2", "score_value": 2}, {"question_id": "D6", "option_id": "D6_1", "score_value": 0}, {"question_id": "A7", "option_id": "A7_3", "score_value": 1}, {"question_id": "D7", "option_id": "D7_3", "score_value": 2}]	2025-12-07 16:32:28.614171+03	2025-12-07 16:32:28.614171+03
a9c1aa5b-f955-43a0-9a8e-d5a009da4b30	1	HADS	1.0	2025-12-07 14:47:47.680976+03	{"ANX": {"score": 9, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}, "DEP": {"score": 10, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}	[{"question_id": "A1", "option_id": "A1_3", "score_value": 1}, {"question_id": "D1", "option_id": "D1_2", "score_value": 1}, {"question_id": "A2", "option_id": "A2_3", "score_value": 1}, {"question_id": "D2", "option_id": "D2_2", "score_value": 1}, {"question_id": "A3", "option_id": "A3_3", "score_value": 1}, {"question_id": "D3", "option_id": "D3_2", "score_value": 1}, {"question_id": "A4", "option_id": "A4_3", "score_value": 1}, {"question_id": "D4", "option_id": "D4_2", "score_value": 2}, {"question_id": "A5", "option_id": "A5_3", "score_value": 1}, {"question_id": "D5", "option_id": "D5_1", "score_value": 3}, {"question_id": "A6", "option_id": "A6_2", "score_value": 2}, {"question_id": "D6", "option_id": "D6_3", "score_value": 2}, {"question_id": "A7", "option_id": "A7_2", "score_value": 2}, {"question_id": "D7", "option_id": "D7_1", "score_value": 0}]	2025-12-07 17:47:47.698467+03	2025-12-07 17:47:47.698467+03
7f6a133b-adf9-44e1-a858-326ad37f6469	1	KOP25A	1.0	2025-12-07 16:06:25.434191+03	{"technical": {"VT": 13, "VS": 20, "VM": 27, "GT": 20, "GS": 25, "GM": 26}, "adherence": {"PT": 28.9, "PS": 55.6, "PM": 78.0, "PL": 49.7}}	[{"question_id": "Q1", "option_id": "Q1_2", "score_value": 2}, {"question_id": "Q2", "option_id": "Q2_2", "score_value": 2}, {"question_id": "Q3", "option_id": "Q3_2", "score_value": 2}, {"question_id": "Q4", "option_id": "Q4_2", "score_value": 2}, {"question_id": "Q5", "option_id": "Q5_2", "score_value": 2}, {"question_id": "Q6", "option_id": "Q6_3", "score_value": 3}, {"question_id": "Q7", "option_id": "Q7_6", "score_value": 6}, {"question_id": "Q8", "option_id": "Q8_6", "score_value": 6}, {"question_id": "Q9", "option_id": "Q9_6", "score_value": 6}, {"question_id": "Q10", "option_id": "Q10_4", "score_value": 4}, {"question_id": "Q11", "option_id": "Q11_6", "score_value": 6}, {"question_id": "Q12", "option_id": "Q12_3", "score_value": 3}, {"question_id": "Q13", "option_id": "Q13_6", "score_value": 6}, {"question_id": "Q14", "option_id": "Q14_4", "score_value": 4}, {"question_id": "Q15", "option_id": "Q15_6", "score_value": 6}, {"question_id": "Q16", "option_id": "Q16_5", "score_value": 5}, {"question_id": "Q17", "option_id": "Q17_4", "score_value": 4}, {"question_id": "Q18", "option_id": "Q18_5", "score_value": 5}, {"question_id": "Q19", "option_id": "Q19_6", "score_value": 6}, {"question_id": "Q20", "option_id": "Q20_4", "score_value": 4}, {"question_id": "Q21", "option_id": "Q21_2", "score_value": 2}, {"question_id": "Q22", "option_id": "Q22_4", "score_value": 4}, {"question_id": "Q23", "option_id": "Q23_6", "score_value": 6}, {"question_id": "Q24", "option_id": "Q24_4", "score_value": 4}, {"question_id": "Q25", "option_id": "Q25_6", "score_value": 6}]	2025-12-07 19:06:25.451801+03	2025-12-07 19:06:25.451801+03
0559a5dd-b750-4a17-9280-e20fdf8b12c9	1	KOP25A	1.0	2025-12-07 16:20:54.792645+03	{"technical": {"VT": 23, "VS": 16, "VM": 21, "GT": 18, "GS": 19, "GM": 22}, "adherence": {"PT": 46.0, "PS": 33.8, "PM": 51.3, "PL": 45.7}}	[{"question_id": "Q1", "option_id": "Q1_3", "score_value": 3}, {"question_id": "Q2", "option_id": "Q2_4", "score_value": 4}, {"question_id": "Q3", "option_id": "Q3_3", "score_value": 3}, {"question_id": "Q4", "option_id": "Q4_6", "score_value": 6}, {"question_id": "Q5", "option_id": "Q5_1", "score_value": 1}, {"question_id": "Q6", "option_id": "Q6_6", "score_value": 6}, {"question_id": "Q7", "option_id": "Q7_6", "score_value": 6}, {"question_id": "Q8", "option_id": "Q8_2", "score_value": 2}, {"question_id": "Q9", "option_id": "Q9_5", "score_value": 5}, {"question_id": "Q10", "option_id": "Q10_3", "score_value": 3}, {"question_id": "Q11", "option_id": "Q11_4", "score_value": 4}, {"question_id": "Q12", "option_id": "Q12_4", "score_value": 4}, {"question_id": "Q13", "option_id": "Q13_5", "score_value": 5}, {"question_id": "Q14", "option_id": "Q14_4", "score_value": 4}, {"question_id": "Q15", "option_id": "Q15_4", "score_value": 4}, {"question_id": "Q16", "option_id": "Q16_3", "score_value": 3}, {"question_id": "Q17", "option_id": "Q17_4", "score_value": 4}, {"question_id": "Q18", "option_id": "Q18_3", "score_value": 3}, {"question_id": "Q19", "option_id": "Q19_4", "score_value": 4}, {"question_id": "Q20", "option_id": "Q20_2", "score_value": 2}, {"question_id": "Q21", "option_id": "Q21_6", "score_value": 6}, {"question_id": "Q22", "option_id": "Q22_5", "score_value": 5}, {"question_id": "Q23", "option_id": "Q23_3", "score_value": 3}, {"question_id": "Q24", "option_id": "Q24_6", "score_value": 6}, {"question_id": "Q25", "option_id": "Q25_4", "score_value": 4}]	2025-12-07 19:20:54.809655+03	2025-12-07 19:20:54.809655+03
770d02b5-c377-4bb1-99f9-d222b9255463	1	KOP25A	1.0	2025-12-07 16:22:16.852991+03	{"technical": {"VT": 5, "VS": 5, "VM": 5, "GT": 5, "GS": 5, "GM": 5}, "adherence": {"PT": 2.8, "PS": 2.8, "PM": 2.8, "PL": 2.8}}	[{"question_id": "Q1", "option_id": "Q1_1", "score_value": 1}, {"question_id": "Q2", "option_id": "Q2_1", "score_value": 1}, {"question_id": "Q3", "option_id": "Q3_1", "score_value": 1}, {"question_id": "Q4", "option_id": "Q4_1", "score_value": 1}, {"question_id": "Q5", "option_id": "Q5_1", "score_value": 1}, {"question_id": "Q6", "option_id": "Q6_1", "score_value": 1}, {"question_id": "Q7", "option_id": "Q7_1", "score_value": 1}, {"question_id": "Q8", "option_id": "Q8_1", "score_value": 1}, {"question_id": "Q9", "option_id": "Q9_1", "score_value": 1}, {"question_id": "Q10", "option_id": "Q10_1", "score_value": 1}, {"question_id": "Q11", "option_id": "Q11_1", "score_value": 1}, {"question_id": "Q12", "option_id": "Q12_1", "score_value": 1}, {"question_id": "Q13", "option_id": "Q13_1", "score_value": 1}, {"question_id": "Q14", "option_id": "Q14_1", "score_value": 1}, {"question_id": "Q15", "option_id": "Q15_1", "score_value": 1}, {"question_id": "Q16", "option_id": "Q16_1", "score_value": 1}, {"question_id": "Q17", "option_id": "Q17_1", "score_value": 1}, {"question_id": "Q18", "option_id": "Q18_1", "score_value": 1}, {"question_id": "Q19", "option_id": "Q19_1", "score_value": 1}, {"question_id": "Q20", "option_id": "Q20_1", "score_value": 1}, {"question_id": "Q21", "option_id": "Q21_1", "score_value": 1}, {"question_id": "Q22", "option_id": "Q22_1", "score_value": 1}, {"question_id": "Q23", "option_id": "Q23_1", "score_value": 1}, {"question_id": "Q24", "option_id": "Q24_1", "score_value": 1}, {"question_id": "Q25", "option_id": "Q25_1", "score_value": 1}]	2025-12-07 19:22:16.854264+03	2025-12-07 19:22:16.854264+03
c36f9961-97c2-4d97-b358-cbc39b07ff24	1	KOP25A	1.0	2025-12-07 16:45:54.87069+03	{"technical": {"VT": 30, "VS": 30, "VM": 30, "GT": 30, "GS": 30, "GM": 30}, "adherence": {"PT": 100.0, "PS": 100.0, "PM": 100.0, "PL": 100.0}}	[{"question_id": "Q1", "option_id": "Q1_6", "score_value": 6}, {"question_id": "Q2", "option_id": "Q2_6", "score_value": 6}, {"question_id": "Q3", "option_id": "Q3_6", "score_value": 6}, {"question_id": "Q4", "option_id": "Q4_6", "score_value": 6}, {"question_id": "Q5", "option_id": "Q5_6", "score_value": 6}, {"question_id": "Q6", "option_id": "Q6_6", "score_value": 6}, {"question_id": "Q7", "option_id": "Q7_6", "score_value": 6}, {"question_id": "Q8", "option_id": "Q8_6", "score_value": 6}, {"question_id": "Q9", "option_id": "Q9_6", "score_value": 6}, {"question_id": "Q10", "option_id": "Q10_6", "score_value": 6}, {"question_id": "Q11", "option_id": "Q11_6", "score_value": 6}, {"question_id": "Q12", "option_id": "Q12_6", "score_value": 6}, {"question_id": "Q13", "option_id": "Q13_6", "score_value": 6}, {"question_id": "Q14", "option_id": "Q14_6", "score_value": 6}, {"question_id": "Q15", "option_id": "Q15_6", "score_value": 6}, {"question_id": "Q16", "option_id": "Q16_6", "score_value": 6}, {"question_id": "Q17", "option_id": "Q17_6", "score_value": 6}, {"question_id": "Q18", "option_id": "Q18_6", "score_value": 6}, {"question_id": "Q19", "option_id": "Q19_6", "score_value": 6}, {"question_id": "Q20", "option_id": "Q20_6", "score_value": 6}, {"question_id": "Q21", "option_id": "Q21_6", "score_value": 6}, {"question_id": "Q22", "option_id": "Q22_6", "score_value": 6}, {"question_id": "Q23", "option_id": "Q23_6", "score_value": 6}, {"question_id": "Q24", "option_id": "Q24_6", "score_value": 6}, {"question_id": "Q25", "option_id": "Q25_6", "score_value": 6}]	2025-12-07 19:45:54.873076+03	2025-12-07 19:45:54.873076+03
1d5b6d90-9442-48f6-9caf-29af0d4a6126	1	KOP25A	1.0	2025-12-07 16:57:38.080714+03	{"technical": {"VT": 19, "VS": 19, "VM": 19, "GT": 15, "GS": 15, "GM": 15}, "adherence": {"PT": 31.7, "PS": 31.7, "PM": 31.7, "PL": 31.7}}	[{"question_id": "Q1", "option_id": "Q1_4", "score_value": 4}, {"question_id": "Q2", "option_id": "Q2_4", "score_value": 4}, {"question_id": "Q3", "option_id": "Q3_4", "score_value": 4}, {"question_id": "Q4", "option_id": "Q4_4", "score_value": 4}, {"question_id": "Q5", "option_id": "Q5_4", "score_value": 4}, {"question_id": "Q6", "option_id": "Q6_4", "score_value": 4}, {"question_id": "Q7", "option_id": "Q7_4", "score_value": 4}, {"question_id": "Q8", "option_id": "Q8_4", "score_value": 4}, {"question_id": "Q9", "option_id": "Q9_4", "score_value": 4}, {"question_id": "Q10", "option_id": "Q10_4", "score_value": 4}, {"question_id": "Q11", "option_id": "Q11_4", "score_value": 4}, {"question_id": "Q12", "option_id": "Q12_4", "score_value": 4}, {"question_id": "Q13", "option_id": "Q13_3", "score_value": 3}, {"question_id": "Q14", "option_id": "Q14_3", "score_value": 3}, {"question_id": "Q15", "option_id": "Q15_3", "score_value": 3}, {"question_id": "Q16", "option_id": "Q16_3", "score_value": 3}, {"question_id": "Q17", "option_id": "Q17_3", "score_value": 3}, {"question_id": "Q18", "option_id": "Q18_3", "score_value": 3}, {"question_id": "Q19", "option_id": "Q19_3", "score_value": 3}, {"question_id": "Q20", "option_id": "Q20_3", "score_value": 3}, {"question_id": "Q21", "option_id": "Q21_3", "score_value": 3}, {"question_id": "Q22", "option_id": "Q22_3", "score_value": 3}, {"question_id": "Q23", "option_id": "Q23_3", "score_value": 3}, {"question_id": "Q24", "option_id": "Q24_3", "score_value": 3}, {"question_id": "Q25", "option_id": "Q25_3", "score_value": 3}]	2025-12-07 19:57:38.082344+03	2025-12-07 19:57:38.082344+03
60260dfd-e5ed-4884-81b7-7f2c87320651	1	KOP25A	1.0	2025-12-07 17:05:20.700238+03	{"technical": {"VT": 15, "VS": 15, "VM": 15, "GT": 15, "GS": 15, "GM": 15}, "adherence": {"PT": 25.0, "PS": 25.0, "PM": 25.0, "PL": 25.0}}	[{"question_id": "Q1", "option_id": "Q1_3", "score_value": 3}, {"question_id": "Q2", "option_id": "Q2_3", "score_value": 3}, {"question_id": "Q3", "option_id": "Q3_3", "score_value": 3}, {"question_id": "Q4", "option_id": "Q4_3", "score_value": 3}, {"question_id": "Q5", "option_id": "Q5_3", "score_value": 3}, {"question_id": "Q6", "option_id": "Q6_3", "score_value": 3}, {"question_id": "Q7", "option_id": "Q7_3", "score_value": 3}, {"question_id": "Q8", "option_id": "Q8_3", "score_value": 3}, {"question_id": "Q9", "option_id": "Q9_3", "score_value": 3}, {"question_id": "Q10", "option_id": "Q10_3", "score_value": 3}, {"question_id": "Q11", "option_id": "Q11_3", "score_value": 3}, {"question_id": "Q12", "option_id": "Q12_3", "score_value": 3}, {"question_id": "Q13", "option_id": "Q13_3", "score_value": 3}, {"question_id": "Q14", "option_id": "Q14_3", "score_value": 3}, {"question_id": "Q15", "option_id": "Q15_3", "score_value": 3}, {"question_id": "Q16", "option_id": "Q16_3", "score_value": 3}, {"question_id": "Q17", "option_id": "Q17_3", "score_value": 3}, {"question_id": "Q18", "option_id": "Q18_3", "score_value": 3}, {"question_id": "Q19", "option_id": "Q19_3", "score_value": 3}, {"question_id": "Q20", "option_id": "Q20_3", "score_value": 3}, {"question_id": "Q21", "option_id": "Q21_3", "score_value": 3}, {"question_id": "Q22", "option_id": "Q22_3", "score_value": 3}, {"question_id": "Q23", "option_id": "Q23_3", "score_value": 3}, {"question_id": "Q24", "option_id": "Q24_3", "score_value": 3}, {"question_id": "Q25", "option_id": "Q25_3", "score_value": 3}]	2025-12-07 20:05:20.702121+03	2025-12-07 20:05:20.702121+03
5da42675-4ba8-432e-a393-dbf42165891f	1	KOP25A	1.0	2025-12-07 17:06:07.662795+03	{"technical": {"VT": 15, "VS": 15, "VM": 15, "GT": 15, "GS": 15, "GM": 15}, "adherence": {"PT": 25.0, "PS": 25.0, "PM": 25.0, "PL": 25.0}}	[{"question_id": "Q1", "option_id": "Q1_3", "score_value": 3}, {"question_id": "Q2", "option_id": "Q2_3", "score_value": 3}, {"question_id": "Q3", "option_id": "Q3_3", "score_value": 3}, {"question_id": "Q4", "option_id": "Q4_3", "score_value": 3}, {"question_id": "Q5", "option_id": "Q5_3", "score_value": 3}, {"question_id": "Q6", "option_id": "Q6_3", "score_value": 3}, {"question_id": "Q7", "option_id": "Q7_3", "score_value": 3}, {"question_id": "Q8", "option_id": "Q8_3", "score_value": 3}, {"question_id": "Q9", "option_id": "Q9_3", "score_value": 3}, {"question_id": "Q10", "option_id": "Q10_3", "score_value": 3}, {"question_id": "Q11", "option_id": "Q11_3", "score_value": 3}, {"question_id": "Q12", "option_id": "Q12_3", "score_value": 3}, {"question_id": "Q13", "option_id": "Q13_3", "score_value": 3}, {"question_id": "Q14", "option_id": "Q14_3", "score_value": 3}, {"question_id": "Q15", "option_id": "Q15_3", "score_value": 3}, {"question_id": "Q16", "option_id": "Q16_3", "score_value": 3}, {"question_id": "Q17", "option_id": "Q17_3", "score_value": 3}, {"question_id": "Q18", "option_id": "Q18_3", "score_value": 3}, {"question_id": "Q19", "option_id": "Q19_3", "score_value": 3}, {"question_id": "Q20", "option_id": "Q20_3", "score_value": 3}, {"question_id": "Q21", "option_id": "Q21_3", "score_value": 3}, {"question_id": "Q22", "option_id": "Q22_3", "score_value": 3}, {"question_id": "Q23", "option_id": "Q23_3", "score_value": 3}, {"question_id": "Q24", "option_id": "Q24_3", "score_value": 3}, {"question_id": "Q25", "option_id": "Q25_3", "score_value": 3}]	2025-12-07 20:06:07.680649+03	2025-12-07 20:06:07.680649+03
b1f74a82-c315-4869-8c65-f424f2f8ca11	1	KOP25A	1.0	2025-12-07 17:06:41.578147+03	{"technical": {"VT": 30, "VS": 30, "VM": 30, "GT": 30, "GS": 30, "GM": 30}, "adherence": {"PT": 100.0, "PS": 100.0, "PM": 100.0, "PL": 100.0}}	[{"question_id": "Q1", "option_id": "Q1_6", "score_value": 6}, {"question_id": "Q2", "option_id": "Q2_6", "score_value": 6}, {"question_id": "Q3", "option_id": "Q3_6", "score_value": 6}, {"question_id": "Q4", "option_id": "Q4_6", "score_value": 6}, {"question_id": "Q5", "option_id": "Q5_6", "score_value": 6}, {"question_id": "Q6", "option_id": "Q6_6", "score_value": 6}, {"question_id": "Q7", "option_id": "Q7_6", "score_value": 6}, {"question_id": "Q8", "option_id": "Q8_6", "score_value": 6}, {"question_id": "Q9", "option_id": "Q9_6", "score_value": 6}, {"question_id": "Q10", "option_id": "Q10_6", "score_value": 6}, {"question_id": "Q11", "option_id": "Q11_6", "score_value": 6}, {"question_id": "Q12", "option_id": "Q12_6", "score_value": 6}, {"question_id": "Q13", "option_id": "Q13_6", "score_value": 6}, {"question_id": "Q14", "option_id": "Q14_6", "score_value": 6}, {"question_id": "Q15", "option_id": "Q15_6", "score_value": 6}, {"question_id": "Q16", "option_id": "Q16_6", "score_value": 6}, {"question_id": "Q17", "option_id": "Q17_6", "score_value": 6}, {"question_id": "Q18", "option_id": "Q18_6", "score_value": 6}, {"question_id": "Q19", "option_id": "Q19_6", "score_value": 6}, {"question_id": "Q20", "option_id": "Q20_6", "score_value": 6}, {"question_id": "Q21", "option_id": "Q21_6", "score_value": 6}, {"question_id": "Q22", "option_id": "Q22_6", "score_value": 6}, {"question_id": "Q23", "option_id": "Q23_6", "score_value": 6}, {"question_id": "Q24", "option_id": "Q24_6", "score_value": 6}, {"question_id": "Q25", "option_id": "Q25_6", "score_value": 6}]	2025-12-07 20:06:41.579749+03	2025-12-07 20:06:41.579749+03
2939d277-2f52-48f4-84d7-26e1ec6a987a	1	KOP25A	1.0	2025-12-07 17:08:08.738246+03	{"technical": {"VT": 25, "VS": 30, "VM": 30, "GT": 30, "GS": 30, "GM": 30}, "adherence": {"PT": 83.3, "PS": 100.0, "PM": 100.0, "PL": 91.7}}	[{"question_id": "Q1", "option_id": "Q1_6", "score_value": 6}, {"question_id": "Q2", "option_id": "Q2_1", "score_value": 1}, {"question_id": "Q3", "option_id": "Q3_6", "score_value": 6}, {"question_id": "Q4", "option_id": "Q4_6", "score_value": 6}, {"question_id": "Q5", "option_id": "Q5_6", "score_value": 6}, {"question_id": "Q6", "option_id": "Q6_6", "score_value": 6}, {"question_id": "Q7", "option_id": "Q7_6", "score_value": 6}, {"question_id": "Q8", "option_id": "Q8_6", "score_value": 6}, {"question_id": "Q9", "option_id": "Q9_6", "score_value": 6}, {"question_id": "Q10", "option_id": "Q10_6", "score_value": 6}, {"question_id": "Q11", "option_id": "Q11_6", "score_value": 6}, {"question_id": "Q12", "option_id": "Q12_6", "score_value": 6}, {"question_id": "Q13", "option_id": "Q13_6", "score_value": 6}, {"question_id": "Q14", "option_id": "Q14_6", "score_value": 6}, {"question_id": "Q15", "option_id": "Q15_6", "score_value": 6}, {"question_id": "Q16", "option_id": "Q16_6", "score_value": 6}, {"question_id": "Q17", "option_id": "Q17_6", "score_value": 6}, {"question_id": "Q18", "option_id": "Q18_6", "score_value": 6}, {"question_id": "Q19", "option_id": "Q19_6", "score_value": 6}, {"question_id": "Q20", "option_id": "Q20_6", "score_value": 6}, {"question_id": "Q21", "option_id": "Q21_6", "score_value": 6}, {"question_id": "Q22", "option_id": "Q22_6", "score_value": 6}, {"question_id": "Q23", "option_id": "Q23_6", "score_value": 6}, {"question_id": "Q24", "option_id": "Q24_6", "score_value": 6}, {"question_id": "Q25", "option_id": "Q25_6", "score_value": 6}]	2025-12-07 20:08:08.739895+03	2025-12-07 20:08:08.739895+03
0dcab2c2-2988-468f-b319-6aeb9b46c294	1	KOP25A	1.0	2025-12-07 18:27:19.049512+03	{"technical": {"VT": 18, "VS": 14, "VM": 10, "GT": 10, "GS": 18, "GM": 26}, "adherence": {"PT": 20.0, "PS": 28.0, "PM": 28.9, "PL": 24.3}}	[{"question_id": "Q1", "option_id": "Q1_4", "score_value": 4}, {"question_id": "Q2", "option_id": "Q2_4", "score_value": 4}, {"question_id": "Q3", "option_id": "Q3_4", "score_value": 4}, {"question_id": "Q4", "option_id": "Q4_4", "score_value": 4}, {"question_id": "Q5", "option_id": "Q5_4", "score_value": 4}, {"question_id": "Q6", "option_id": "Q6_4", "score_value": 4}, {"question_id": "Q7", "option_id": "Q7_2", "score_value": 2}, {"question_id": "Q8", "option_id": "Q8_2", "score_value": 2}, {"question_id": "Q9", "option_id": "Q9_2", "score_value": 2}, {"question_id": "Q10", "option_id": "Q10_2", "score_value": 2}, {"question_id": "Q11", "option_id": "Q11_2", "score_value": 2}, {"question_id": "Q12", "option_id": "Q12_2", "score_value": 2}, {"question_id": "Q13", "option_id": "Q13_2", "score_value": 2}, {"question_id": "Q14", "option_id": "Q14_2", "score_value": 2}, {"question_id": "Q15", "option_id": "Q15_2", "score_value": 2}, {"question_id": "Q16", "option_id": "Q16_2", "score_value": 2}, {"question_id": "Q17", "option_id": "Q17_2", "score_value": 2}, {"question_id": "Q18", "option_id": "Q18_2", "score_value": 2}, {"question_id": "Q19", "option_id": "Q19_2", "score_value": 2}, {"question_id": "Q20", "option_id": "Q20_2", "score_value": 2}, {"question_id": "Q21", "option_id": "Q21_2", "score_value": 2}, {"question_id": "Q22", "option_id": "Q22_6", "score_value": 6}, {"question_id": "Q23", "option_id": "Q23_6", "score_value": 6}, {"question_id": "Q24", "option_id": "Q24_6", "score_value": 6}, {"question_id": "Q25", "option_id": "Q25_6", "score_value": 6}]	2025-12-07 21:27:19.054369+03	2025-12-07 21:27:19.054369+03
f3ad4016-7d50-4260-908a-0e68c8fd8d72	1	KOP25A	1.0	2025-12-07 19:15:54.14782+03	{"technical": {"VT": 30, "VS": 30, "VM": 30, "GT": 30, "GS": 30, "GM": 30}, "adherence": {"PT": 100.0, "PS": 100.0, "PM": 100.0, "PL": 100.0}, "total_score": 100.0, "adherence_level": "high", "adherence_label": "\\u0412\\u044b\\u0441\\u043e\\u043a\\u0430\\u044f \\u043f\\u0440\\u0438\\u0432\\u0435\\u0440\\u0436\\u0435\\u043d\\u043d\\u043e\\u0441\\u0442\\u044c", "summary": "\\u0412\\u044b\\u0441\\u043e\\u043a\\u0430\\u044f \\u043f\\u0440\\u0438\\u0432\\u0435\\u0440\\u0436\\u0435\\u043d\\u043d\\u043e\\u0441\\u0442\\u044c. \\u0418\\u0442\\u043e\\u0433\\u043e\\u0432\\u044b\\u0439 \\u0438\\u043d\\u0434\\u0435\\u043a\\u0441: 100.0%."}	[{"question_id": "Q1", "option_id": "Q1_6", "score_value": 6}, {"question_id": "Q2", "option_id": "Q2_6", "score_value": 6}, {"question_id": "Q3", "option_id": "Q3_6", "score_value": 6}, {"question_id": "Q4", "option_id": "Q4_6", "score_value": 6}, {"question_id": "Q5", "option_id": "Q5_6", "score_value": 6}, {"question_id": "Q6", "option_id": "Q6_6", "score_value": 6}, {"question_id": "Q7", "option_id": "Q7_6", "score_value": 6}, {"question_id": "Q8", "option_id": "Q8_6", "score_value": 6}, {"question_id": "Q9", "option_id": "Q9_6", "score_value": 6}, {"question_id": "Q10", "option_id": "Q10_6", "score_value": 6}, {"question_id": "Q11", "option_id": "Q11_6", "score_value": 6}, {"question_id": "Q12", "option_id": "Q12_6", "score_value": 6}, {"question_id": "Q13", "option_id": "Q13_6", "score_value": 6}, {"question_id": "Q14", "option_id": "Q14_6", "score_value": 6}, {"question_id": "Q15", "option_id": "Q15_6", "score_value": 6}, {"question_id": "Q16", "option_id": "Q16_6", "score_value": 6}, {"question_id": "Q17", "option_id": "Q17_6", "score_value": 6}, {"question_id": "Q18", "option_id": "Q18_6", "score_value": 6}, {"question_id": "Q19", "option_id": "Q19_6", "score_value": 6}, {"question_id": "Q20", "option_id": "Q20_6", "score_value": 6}, {"question_id": "Q21", "option_id": "Q21_6", "score_value": 6}, {"question_id": "Q22", "option_id": "Q22_6", "score_value": 6}, {"question_id": "Q23", "option_id": "Q23_6", "score_value": 6}, {"question_id": "Q24", "option_id": "Q24_6", "score_value": 6}, {"question_id": "Q25", "option_id": "Q25_6", "score_value": 6}]	2025-12-07 22:15:54.137059+03	2025-12-07 22:15:54.137059+03
6e48a124-2f48-47b9-88cf-3ee2a88905cc	1	HADS	1.0	2025-12-07 19:40:13.816166+03	{"total_score": 23, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b (14 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430 (9 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 14, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "depression": {"score": 9, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}, "anxiety_score": 14, "depression_score": 9, "anxiety_level": "clinical", "depression_level": "borderline", "total_level": "clinical", "total_label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b", "ANX": {"score": 14, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 9, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}	[{"question_id": "A1", "option_id": "A1_2", "score_value": 2}, {"question_id": "D1", "option_id": "D1_2", "score_value": 1}, {"question_id": "A2", "option_id": "A2_2", "score_value": 2}, {"question_id": "D2", "option_id": "D2_2", "score_value": 1}, {"question_id": "A3", "option_id": "A3_2", "score_value": 2}, {"question_id": "D3", "option_id": "D3_2", "score_value": 1}, {"question_id": "A4", "option_id": "A4_2", "score_value": 2}, {"question_id": "D4", "option_id": "D4_2", "score_value": 2}, {"question_id": "A5", "option_id": "A5_2", "score_value": 2}, {"question_id": "D5", "option_id": "D5_2", "score_value": 2}, {"question_id": "A6", "option_id": "A6_2", "score_value": 2}, {"question_id": "D6", "option_id": "D6_2", "score_value": 1}, {"question_id": "A7", "option_id": "A7_2", "score_value": 2}, {"question_id": "D7", "option_id": "D7_2", "score_value": 1}]	2025-12-07 22:40:13.815795+03	2025-12-07 22:40:13.815795+03
2456f17d-c99d-4942-b883-3eb17ad900de	1	HADS	1.0	2025-12-08 05:20:43.008188+03	{"total_score": 4, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041d\\u043e\\u0440\\u043c\\u0430 (0 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041d\\u043e\\u0440\\u043c\\u0430 (4 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 0, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}, "depression": {"score": 4, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}}, "anxiety_score": 0, "depression_score": 4, "anxiety_level": "normal", "depression_level": "normal", "total_level": "normal", "total_label": "\\u041d\\u043e\\u0440\\u043c\\u0430", "ANX": {"score": 0, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}, "DEP": {"score": 4, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}}	[{"question_id": "A1", "option_id": "A1_4", "score_value": 0}, {"question_id": "D1", "option_id": "D1_1", "score_value": 0}, {"question_id": "A2", "option_id": "A2_4", "score_value": 0}, {"question_id": "D2", "option_id": "D2_1", "score_value": 0}, {"question_id": "A3", "option_id": "A3_4", "score_value": 0}, {"question_id": "D3", "option_id": "D3_2", "score_value": 1}, {"question_id": "A4", "option_id": "A4_4", "score_value": 0}, {"question_id": "D4", "option_id": "D4_3", "score_value": 1}, {"question_id": "A5", "option_id": "A5_4", "score_value": 0}, {"question_id": "D5", "option_id": "D5_3", "score_value": 1}, {"question_id": "A6", "option_id": "A6_4", "score_value": 0}, {"question_id": "D6", "option_id": "D6_1", "score_value": 0}, {"question_id": "A7", "option_id": "A7_4", "score_value": 0}, {"question_id": "D7", "option_id": "D7_2", "score_value": 1}]	2025-12-08 08:20:43.007711+03	2025-12-08 08:20:43.007711+03
f424ba7a-669f-428d-9cd6-1dc2bc83087f	1	HADS	1.0	2025-12-08 09:28:50.271849+03	{"total_score": 23, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b (14 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430 (9 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 14, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "depression": {"score": 9, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}, "anxiety_score": 14, "depression_score": 9, "anxiety_level": "clinical", "depression_level": "borderline", "total_level": "clinical", "total_label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b", "ANX": {"score": 14, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 9, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}	[{"question_id": "A1", "option_id": "A1_2", "score_value": 2}, {"question_id": "D1", "option_id": "D1_2", "score_value": 1}, {"question_id": "A2", "option_id": "A2_2", "score_value": 2}, {"question_id": "D2", "option_id": "D2_2", "score_value": 1}, {"question_id": "A3", "option_id": "A3_2", "score_value": 2}, {"question_id": "D3", "option_id": "D3_2", "score_value": 1}, {"question_id": "A4", "option_id": "A4_2", "score_value": 2}, {"question_id": "D4", "option_id": "D4_2", "score_value": 2}, {"question_id": "A5", "option_id": "A5_2", "score_value": 2}, {"question_id": "D5", "option_id": "D5_2", "score_value": 2}, {"question_id": "A6", "option_id": "A6_2", "score_value": 2}, {"question_id": "D6", "option_id": "D6_2", "score_value": 1}, {"question_id": "A7", "option_id": "A7_2", "score_value": 2}, {"question_id": "D7", "option_id": "D7_2", "score_value": 1}]	2025-12-08 12:28:50.265716+03	2025-12-08 12:28:50.265716+03
ffe04782-ce61-47d3-8400-4caf4e55d5a4	1	TOBOL	1.0	2025-12-08 09:56:30.290347+03	{"total_score": 7, "summary": "\\u0412\\u0435\\u0434\\u0443\\u0449\\u0438\\u0439 \\u0442\\u0438\\u043f \\u043e\\u0442\\u043d\\u043e\\u0448\\u0435\\u043d\\u0438\\u044f \\u043a \\u0431\\u043e\\u043b\\u0435\\u0437\\u043d\\u0438: \\u041d\\u0435\\u0432\\u0440\\u0430\\u0441\\u0442\\u0435\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439 (\\u041d).", "subscales": {"A": {"score": 3, "label": "\\u0410\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "G": {"score": 0, "label": "\\u0413\\u0430\\u0440\\u043c\\u043e\\u043d\\u0438\\u0447\\u043d\\u044b\\u0439", "adaptive": true}, "D": {"score": 0, "label": "\\u0414\\u0438\\u0441\\u0444\\u043e\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "Z": {"score": 0, "label": "\\u0410\\u043d\\u043e\\u0437\\u043e\\u0433\\u043d\\u043e\\u0437\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "I": {"score": 5, "label": "\\u0418\\u043f\\u043e\\u0445\\u043e\\u043d\\u0434\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "M": {"score": 4, "label": "\\u041c\\u0435\\u043b\\u0430\\u043d\\u0445\\u043e\\u043b\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "N": {"score": 7, "label": "\\u041d\\u0435\\u0432\\u0440\\u0430\\u0441\\u0442\\u0435\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "P": {"score": 3, "label": "\\u041f\\u0430\\u0440\\u0430\\u043d\\u043e\\u0439\\u044f\\u043b\\u044c\\u043d\\u044b\\u0439", "adaptive": false}, "R": {"score": 0, "label": "\\u042d\\u0440\\u0433\\u043e\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": true}, "S": {"score": 0, "label": "\\u0421\\u0435\\u043d\\u0441\\u0438\\u0442\\u0438\\u0432\\u043d\\u044b\\u0439", "adaptive": false}, "T": {"score": 4, "label": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0436\\u043d\\u044b\\u0439", "adaptive": false}, "E": {"score": 3, "label": "\\u042d\\u0433\\u043e\\u0446\\u0435\\u043d\\u0442\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}}, "raw": {"type_scores_ru": {"\\u0410": 3, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 5, "\\u041c": 4, "\\u041d": 7, "\\u041f": 3, "\\u0420": 0, "\\u0421": 0, "\\u0422": 4, "\\u042d": 3}, "forbidden_types_ru": [], "leading_types_ru": ["\\u041d"]}}	[{"question_id": "I_1", "option_id": "1", "topic": "I", "row": "1", "coeffs": {"\\u0410": 3, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 5, "\\u041c": 4, "\\u041d": 3, "\\u041f": 3, "\\u0420": 0, "\\u0421": 0, "\\u0422": 4, "\\u042d": 3}}, {"question_id": "I_6", "option_id": "6", "topic": "I", "row": "6", "coeffs": {"\\u0410": 0, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 0, "\\u041c": 0, "\\u041d": 4, "\\u041f": 0, "\\u0420": 0, "\\u0421": 0, "\\u0422": 0, "\\u042d": 0}}]	2025-12-08 12:56:30.289539+03	2025-12-08 12:56:30.289539+03
5135dbb2-bb61-4dfc-9f92-4b7b89de001c	1	TOBOL	1.0	2025-12-08 10:06:43.068537+03	{"total_score": 5, "summary": "\\u0412\\u0435\\u0434\\u0443\\u0449\\u0438\\u0435 \\u0442\\u0438\\u043f\\u044b \\u043e\\u0442\\u043d\\u043e\\u0448\\u0435\\u043d\\u0438\\u044f \\u043a \\u0431\\u043e\\u043b\\u0435\\u0437\\u043d\\u0438: \\u0410\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439 (\\u0410), \\u0422\\u0440\\u0435\\u0432\\u043e\\u0436\\u043d\\u044b\\u0439 (\\u0422).", "subscales": {"A": {"score": 5, "label": "\\u0410\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "G": {"score": 0, "label": "\\u0413\\u0430\\u0440\\u043c\\u043e\\u043d\\u0438\\u0447\\u043d\\u044b\\u0439", "adaptive": true}, "D": {"score": 0, "label": "\\u0414\\u0438\\u0441\\u0444\\u043e\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "Z": {"score": 0, "label": "\\u0410\\u043d\\u043e\\u0437\\u043e\\u0433\\u043d\\u043e\\u0437\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "I": {"score": 4, "label": "\\u0418\\u043f\\u043e\\u0445\\u043e\\u043d\\u0434\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "M": {"score": 4, "label": "\\u041c\\u0435\\u043b\\u0430\\u043d\\u0445\\u043e\\u043b\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "N": {"score": 3, "label": "\\u041d\\u0435\\u0432\\u0440\\u0430\\u0441\\u0442\\u0435\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "P": {"score": 0, "label": "\\u041f\\u0430\\u0440\\u0430\\u043d\\u043e\\u0439\\u044f\\u043b\\u044c\\u043d\\u044b\\u0439", "adaptive": false}, "R": {"score": 0, "label": "\\u042d\\u0440\\u0433\\u043e\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": true}, "S": {"score": 3, "label": "\\u0421\\u0435\\u043d\\u0441\\u0438\\u0442\\u0438\\u0432\\u043d\\u044b\\u0439", "adaptive": false}, "T": {"score": 5, "label": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0436\\u043d\\u044b\\u0439", "adaptive": false}, "E": {"score": 0, "label": "\\u042d\\u0433\\u043e\\u0446\\u0435\\u043d\\u0442\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}}, "raw": {"type_scores_ru": {"\\u0410": 5, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 4, "\\u041c": 4, "\\u041d": 3, "\\u041f": 0, "\\u0420": 0, "\\u0421": 3, "\\u0422": 5, "\\u042d": 0}, "forbidden_types_ru": ["\\u0413", "\\u0417"], "leading_types_ru": ["\\u0410", "\\u0422"]}}	[{"question_id": "XII_8", "option_id": "1", "topic": "XII", "row": "8", "coeffs": {"\\u0410": 0, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 4, "\\u041c": 0, "\\u041d": 3, "\\u041f": 0, "\\u0420": 0, "\\u0421": 3, "\\u0422": 5, "\\u042d": 0}}, {"question_id": "XII_7", "option_id": "1", "topic": "XII", "row": "7", "coeffs": {"\\u0410": 5, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 0, "\\u041c": 4, "\\u041d": 0, "\\u041f": 0, "\\u0420": 0, "\\u0421": 0, "\\u0422": 0, "\\u042d": 0}}]	2025-12-08 13:06:43.068225+03	2025-12-08 13:06:43.068225+03
dd2c7759-8f48-40eb-b1ce-3617de45dc28	1	HADS	1.0	2025-12-08 10:32:28.792867+03	{"total_score": 19, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041d\\u043e\\u0440\\u043c\\u0430 (7 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b (12 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 7, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}, "depression": {"score": 12, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}}, "anxiety_score": 7, "depression_score": 12, "anxiety_level": "normal", "depression_level": "clinical", "total_level": "clinical", "total_label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b", "ANX": {"score": 7, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}, "DEP": {"score": 12, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}}	[{"question_id": "A1", "option_id": "A1_3", "score_value": 1}, {"question_id": "D1", "option_id": "D1_3", "score_value": 2}, {"question_id": "A2", "option_id": "A2_3", "score_value": 1}, {"question_id": "D2", "option_id": "D2_3", "score_value": 2}, {"question_id": "A3", "option_id": "A3_3", "score_value": 1}, {"question_id": "D3", "option_id": "D3_3", "score_value": 2}, {"question_id": "A4", "option_id": "A4_3", "score_value": 1}, {"question_id": "D4", "option_id": "D4_3", "score_value": 1}, {"question_id": "A5", "option_id": "A5_3", "score_value": 1}, {"question_id": "D5", "option_id": "D5_3", "score_value": 1}, {"question_id": "A6", "option_id": "A6_3", "score_value": 1}, {"question_id": "D6", "option_id": "D6_3", "score_value": 2}, {"question_id": "A7", "option_id": "A7_3", "score_value": 1}, {"question_id": "D7", "option_id": "D7_3", "score_value": 2}]	2025-12-08 13:32:28.792756+03	2025-12-08 13:32:28.792756+03
5289997c-7b81-4166-9b57-35a51d349dbc	1	TOBOL	1.0	2025-12-08 14:19:36.221846+03	{"total_score": 10, "summary": "\\u0412\\u0435\\u0434\\u0443\\u0449\\u0438\\u0439 \\u0442\\u0438\\u043f \\u043e\\u0442\\u043d\\u043e\\u0448\\u0435\\u043d\\u0438\\u044f \\u043a \\u0431\\u043e\\u043b\\u0435\\u0437\\u043d\\u0438: \\u0418\\u043f\\u043e\\u0445\\u043e\\u043d\\u0434\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439 (\\u0418).", "subscales": {"A": {"score": 3, "label": "\\u0410\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "G": {"score": 0, "label": "\\u0413\\u0430\\u0440\\u043c\\u043e\\u043d\\u0438\\u0447\\u043d\\u044b\\u0439", "adaptive": true}, "D": {"score": 0, "label": "\\u0414\\u0438\\u0441\\u0444\\u043e\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "Z": {"score": 0, "label": "\\u0410\\u043d\\u043e\\u0437\\u043e\\u0433\\u043d\\u043e\\u0437\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "I": {"score": 10, "label": "\\u0418\\u043f\\u043e\\u0445\\u043e\\u043d\\u0434\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "M": {"score": 4, "label": "\\u041c\\u0435\\u043b\\u0430\\u043d\\u0445\\u043e\\u043b\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "N": {"score": 3, "label": "\\u041d\\u0435\\u0432\\u0440\\u0430\\u0441\\u0442\\u0435\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "P": {"score": 3, "label": "\\u041f\\u0430\\u0440\\u0430\\u043d\\u043e\\u0439\\u044f\\u043b\\u044c\\u043d\\u044b\\u0439", "adaptive": false}, "R": {"score": 0, "label": "\\u042d\\u0440\\u0433\\u043e\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": true}, "S": {"score": 0, "label": "\\u0421\\u0435\\u043d\\u0441\\u0438\\u0442\\u0438\\u0432\\u043d\\u044b\\u0439", "adaptive": false}, "T": {"score": 4, "label": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0436\\u043d\\u044b\\u0439", "adaptive": false}, "E": {"score": 3, "label": "\\u042d\\u0433\\u043e\\u0446\\u0435\\u043d\\u0442\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}}, "raw": {"type_scores_ru": {"\\u0410": 3, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 10, "\\u041c": 4, "\\u041d": 3, "\\u041f": 3, "\\u0420": 0, "\\u0421": 0, "\\u0422": 4, "\\u042d": 3}, "forbidden_types_ru": ["\\u0417"], "leading_types_ru": ["\\u0418"]}}	[{"question_id": "I_1", "option_id": "1", "topic": "I", "row": "1", "coeffs": {"\\u0410": 3, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 5, "\\u041c": 4, "\\u041d": 3, "\\u041f": 3, "\\u0420": 0, "\\u0421": 0, "\\u0422": 4, "\\u042d": 3}}, {"question_id": "I_5", "option_id": "1", "topic": "I", "row": "5", "coeffs": {"\\u0410": 0, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 5, "\\u041c": 0, "\\u041d": 0, "\\u041f": 0, "\\u0420": 0, "\\u0421": 0, "\\u0422": 0, "\\u042d": 0}}]	2025-12-08 17:19:36.221552+03	2025-12-08 17:19:36.221552+03
c0f3a990-1043-4620-9246-41a842eceddb	1	HADS	1.0	2025-12-08 17:01:08.079327+03	{"total_score": 18, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b (11 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041d\\u043e\\u0440\\u043c\\u0430 (7 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 11, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "depression": {"score": 7, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}}, "anxiety_score": 11, "depression_score": 7, "anxiety_level": "clinical", "depression_level": "normal", "total_level": "clinical", "total_label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b", "ANX": {"score": 11, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 7, "level": "normal", "label": "\\u041d\\u043e\\u0440\\u043c\\u0430"}}	[{"question_id": "A1", "option_id": "A1_2", "score_value": 2}, {"question_id": "D1", "option_id": "D1_1", "score_value": 0}, {"question_id": "A2", "option_id": "A2_1", "score_value": 3}, {"question_id": "D2", "option_id": "D2_2", "score_value": 1}, {"question_id": "A3", "option_id": "A3_2", "score_value": 2}, {"question_id": "D3", "option_id": "D3_2", "score_value": 1}, {"question_id": "A4", "option_id": "A4_3", "score_value": 1}, {"question_id": "D4", "option_id": "D4_3", "score_value": 1}, {"question_id": "A5", "option_id": "A5_3", "score_value": 1}, {"question_id": "D5", "option_id": "D5_3", "score_value": 1}, {"question_id": "A6", "option_id": "A6_3", "score_value": 1}, {"question_id": "D6", "option_id": "D6_2", "score_value": 1}, {"question_id": "A7", "option_id": "A7_3", "score_value": 1}, {"question_id": "D7", "option_id": "D7_3", "score_value": 2}]	2025-12-08 20:01:08.078187+03	2025-12-08 20:01:08.078187+03
226b3f1f-0f48-47fa-92bc-f1f9317c8060	1	HADS	1.0	2025-12-08 17:18:51.418279+03	{"total_score": 23, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b (14 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430 (9 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 14, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "depression": {"score": 9, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}, "anxiety_score": 14, "depression_score": 9, "anxiety_level": "clinical", "depression_level": "borderline", "total_level": "clinical", "total_label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b", "ANX": {"score": 14, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 9, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}	[{"question_id": "A1", "option_id": "A1_2", "score_value": 2}, {"question_id": "D1", "option_id": "D1_2", "score_value": 1}, {"question_id": "A2", "option_id": "A2_2", "score_value": 2}, {"question_id": "D2", "option_id": "D2_2", "score_value": 1}, {"question_id": "A3", "option_id": "A3_2", "score_value": 2}, {"question_id": "D3", "option_id": "D3_2", "score_value": 1}, {"question_id": "A4", "option_id": "A4_2", "score_value": 2}, {"question_id": "D4", "option_id": "D4_2", "score_value": 2}, {"question_id": "A5", "option_id": "A5_2", "score_value": 2}, {"question_id": "D5", "option_id": "D5_2", "score_value": 2}, {"question_id": "A6", "option_id": "A6_2", "score_value": 2}, {"question_id": "D6", "option_id": "D6_2", "score_value": 1}, {"question_id": "A7", "option_id": "A7_2", "score_value": 2}, {"question_id": "D7", "option_id": "D7_2", "score_value": 1}]	2025-12-08 20:18:51.417947+03	2025-12-08 20:18:51.417947+03
b6bce322-af86-4fac-9c3e-2221867c89f5	1	HADS	1.0	2025-12-08 17:21:34.410357+03	{"total_score": 18, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430 (8 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430 (10 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 8, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}, "depression": {"score": 10, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}, "anxiety_score": 8, "depression_score": 10, "anxiety_level": "borderline", "depression_level": "borderline", "total_level": "borderline", "total_label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430", "ANX": {"score": 8, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}, "DEP": {"score": 10, "level": "borderline", "label": "\\u041f\\u043e\\u0433\\u0440\\u0430\\u043d\\u0438\\u0447\\u043d\\u0430\\u044f \\u0437\\u043e\\u043d\\u0430"}}	[{"question_id": "A1", "option_id": "A1_3", "score_value": 1}, {"question_id": "D1", "option_id": "D1_2", "score_value": 1}, {"question_id": "A2", "option_id": "A2_2", "score_value": 2}, {"question_id": "D2", "option_id": "D2_3", "score_value": 2}, {"question_id": "A3", "option_id": "A3_3", "score_value": 1}, {"question_id": "D3", "option_id": "D3_3", "score_value": 2}, {"question_id": "A4", "option_id": "A4_3", "score_value": 1}, {"question_id": "D4", "option_id": "D4_3", "score_value": 1}, {"question_id": "A5", "option_id": "A5_3", "score_value": 1}, {"question_id": "D5", "option_id": "D5_3", "score_value": 1}, {"question_id": "A6", "option_id": "A6_3", "score_value": 1}, {"question_id": "D6", "option_id": "D6_2", "score_value": 1}, {"question_id": "A7", "option_id": "A7_3", "score_value": 1}, {"question_id": "D7", "option_id": "D7_3", "score_value": 2}]	2025-12-08 20:21:34.409534+03	2025-12-08 20:21:34.409534+03
aeb217fb-6a71-4742-be76-2e57c16d0654	1	TOBOL	1.0	2025-12-08 17:32:14.119547+03	{"total_score": 4, "summary": "\\u0412\\u0435\\u0434\\u0443\\u0449\\u0438\\u0439 \\u0442\\u0438\\u043f \\u043e\\u0442\\u043d\\u043e\\u0448\\u0435\\u043d\\u0438\\u044f \\u043a \\u0431\\u043e\\u043b\\u0435\\u0437\\u043d\\u0438: \\u0422\\u0440\\u0435\\u0432\\u043e\\u0436\\u043d\\u044b\\u0439 (\\u0422).", "subscales": {"A": {"score": 3, "label": "\\u0410\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "G": {"score": 0, "label": "\\u0413\\u0430\\u0440\\u043c\\u043e\\u043d\\u0438\\u0447\\u043d\\u044b\\u0439", "adaptive": true}, "D": {"score": 0, "label": "\\u0414\\u0438\\u0441\\u0444\\u043e\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "Z": {"score": 0, "label": "\\u0410\\u043d\\u043e\\u0437\\u043e\\u0433\\u043d\\u043e\\u0437\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "I": {"score": 0, "label": "\\u0418\\u043f\\u043e\\u0445\\u043e\\u043d\\u0434\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "M": {"score": 0, "label": "\\u041c\\u0435\\u043b\\u0430\\u043d\\u0445\\u043e\\u043b\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "N": {"score": 0, "label": "\\u041d\\u0435\\u0432\\u0440\\u0430\\u0441\\u0442\\u0435\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}, "P": {"score": 0, "label": "\\u041f\\u0430\\u0440\\u0430\\u043d\\u043e\\u0439\\u044f\\u043b\\u044c\\u043d\\u044b\\u0439", "adaptive": false}, "R": {"score": 0, "label": "\\u042d\\u0440\\u0433\\u043e\\u043f\\u0430\\u0442\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": true}, "S": {"score": 0, "label": "\\u0421\\u0435\\u043d\\u0441\\u0438\\u0442\\u0438\\u0432\\u043d\\u044b\\u0439", "adaptive": false}, "T": {"score": 4, "label": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0436\\u043d\\u044b\\u0439", "adaptive": false}, "E": {"score": 0, "label": "\\u042d\\u0433\\u043e\\u0446\\u0435\\u043d\\u0442\\u0440\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438\\u0439", "adaptive": false}}, "raw": {"type_scores_ru": {"\\u0410": 3, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 0, "\\u041c": 0, "\\u041d": 0, "\\u041f": 0, "\\u0420": 0, "\\u0421": 0, "\\u0422": 4, "\\u042d": 0}, "forbidden_types_ru": [], "leading_types_ru": ["\\u0422"]}}	[{"question_id": "I_7", "option_id": "1", "topic": "I", "row": "7", "coeffs": {"\\u0410": 0, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 0, "\\u041c": 0, "\\u041d": 0, "\\u041f": 0, "\\u0420": 0, "\\u0421": 0, "\\u0422": 4, "\\u042d": 0}}, {"question_id": "I_12", "option_id": "1", "topic": "I", "row": "12", "coeffs": {"\\u0410": 3, "\\u0413": 0, "\\u0414": 0, "\\u0417": 0, "\\u0418": 0, "\\u041c": 0, "\\u041d": 0, "\\u041f": 0, "\\u0420": 0, "\\u0421": 0, "\\u0422": 0, "\\u042d": 0}}]	2025-12-08 20:32:14.119154+03	2025-12-08 20:32:14.119154+03
29abab3f-de24-4749-9549-d837f2a39208	1	KOP25A	1.0	2025-12-08 17:43:20.909755+03	{"technical": {"VT": 30, "VS": 30, "VM": 30, "GT": 30, "GS": 30, "GM": 30}, "adherence": {"PT": 100.0, "PS": 100.0, "PM": 100.0, "PL": 100.0}, "total_score": 100.0, "adherence_level": "high", "adherence_label": "\\u0412\\u044b\\u0441\\u043e\\u043a\\u0430\\u044f \\u043f\\u0440\\u0438\\u0432\\u0435\\u0440\\u0436\\u0435\\u043d\\u043d\\u043e\\u0441\\u0442\\u044c", "summary": "\\u0412\\u044b\\u0441\\u043e\\u043a\\u0430\\u044f \\u043f\\u0440\\u0438\\u0432\\u0435\\u0440\\u0436\\u0435\\u043d\\u043d\\u043e\\u0441\\u0442\\u044c. \\u0418\\u0442\\u043e\\u0433\\u043e\\u0432\\u044b\\u0439 \\u0438\\u043d\\u0434\\u0435\\u043a\\u0441: 100.0%."}	[{"question_id": "Q1", "option_id": "Q1_6", "score_value": 6}, {"question_id": "Q2", "option_id": "Q2_6", "score_value": 6}, {"question_id": "Q3", "option_id": "Q3_6", "score_value": 6}, {"question_id": "Q4", "option_id": "Q4_6", "score_value": 6}, {"question_id": "Q5", "option_id": "Q5_6", "score_value": 6}, {"question_id": "Q6", "option_id": "Q6_6", "score_value": 6}, {"question_id": "Q7", "option_id": "Q7_6", "score_value": 6}, {"question_id": "Q8", "option_id": "Q8_6", "score_value": 6}, {"question_id": "Q9", "option_id": "Q9_6", "score_value": 6}, {"question_id": "Q10", "option_id": "Q10_6", "score_value": 6}, {"question_id": "Q11", "option_id": "Q11_6", "score_value": 6}, {"question_id": "Q12", "option_id": "Q12_6", "score_value": 6}, {"question_id": "Q13", "option_id": "Q13_6", "score_value": 6}, {"question_id": "Q14", "option_id": "Q14_6", "score_value": 6}, {"question_id": "Q15", "option_id": "Q15_6", "score_value": 6}, {"question_id": "Q16", "option_id": "Q16_6", "score_value": 6}, {"question_id": "Q17", "option_id": "Q17_6", "score_value": 6}, {"question_id": "Q18", "option_id": "Q18_6", "score_value": 6}, {"question_id": "Q19", "option_id": "Q19_6", "score_value": 6}, {"question_id": "Q20", "option_id": "Q20_6", "score_value": 6}, {"question_id": "Q21", "option_id": "Q21_6", "score_value": 6}, {"question_id": "Q22", "option_id": "Q22_6", "score_value": 6}, {"question_id": "Q23", "option_id": "Q23_6", "score_value": 6}, {"question_id": "Q24", "option_id": "Q24_6", "score_value": 6}, {"question_id": "Q25", "option_id": "Q25_6", "score_value": 6}]	2025-12-08 20:43:20.909367+03	2025-12-08 20:43:20.909367+03
b805b43c-a39a-4c32-87a0-3bad8a06cf78	1	HADS	1.0	2025-12-22 22:47:59.144514+03	{"total_score": 24, "summary": "\\u0422\\u0440\\u0435\\u0432\\u043e\\u0433\\u0430: \\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b (12 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432), \\u0434\\u0435\\u043f\\u0440\\u0435\\u0441\\u0441\\u0438\\u044f: \\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b (12 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432)", "subscales": {"anxiety": {"score": 12, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "depression": {"score": 12, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}}, "anxiety_score": 12, "depression_score": 12, "anxiety_level": "clinical", "depression_level": "clinical", "total_level": "clinical", "total_label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b", "ANX": {"score": 12, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}, "DEP": {"score": 12, "level": "clinical", "label": "\\u041a\\u043b\\u0438\\u043d\\u0438\\u0447\\u0435\\u0441\\u043a\\u0438 \\u0437\\u043d\\u0430\\u0447\\u0438\\u043c\\u044b\\u0435 \\u0441\\u0438\\u043c\\u043f\\u0442\\u043e\\u043c\\u044b"}}	[{"question_id": "A1", "option_id": "A1_3", "score_value": 1}, {"question_id": "D1", "option_id": "D1_3", "score_value": 2}, {"question_id": "A2", "option_id": "A2_2", "score_value": 2}, {"question_id": "D2", "option_id": "D2_3", "score_value": 2}, {"question_id": "A3", "option_id": "A3_2", "score_value": 2}, {"question_id": "D3", "option_id": "D3_3", "score_value": 2}, {"question_id": "A4", "option_id": "A4_2", "score_value": 2}, {"question_id": "D4", "option_id": "D4_3", "score_value": 1}, {"question_id": "A5", "option_id": "A5_2", "score_value": 2}, {"question_id": "D5", "option_id": "D5_2", "score_value": 2}, {"question_id": "A6", "option_id": "A6_2", "score_value": 2}, {"question_id": "D6", "option_id": "D6_2", "score_value": 1}, {"question_id": "A7", "option_id": "A7_3", "score_value": 1}, {"question_id": "D7", "option_id": "D7_3", "score_value": 2}]	2025-12-23 01:47:59.143848+03	2025-12-23 01:47:59.143848+03
ab19d044-dc59-441b-b08c-078e41018a2a	1	PSQI	1.0	2026-02-07 14:39:42.881005+03	{"total_score": 14, "summary": "PSQI: 14 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432 \\u2014 \\u0417\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043d\\u0430\\u0440\\u0443\\u0448\\u0435\\u043d\\u0438\\u044f \\u0441\\u043d\\u0430", "level": "significant", "label": "\\u0417\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043d\\u0430\\u0440\\u0443\\u0448\\u0435\\u043d\\u0438\\u044f \\u0441\\u043d\\u0430", "components": {"C1_subjective_quality": 3, "C2_sleep_latency": 2, "C3_sleep_duration": 0, "C4_sleep_efficiency": 0, "C5_sleep_disturbances": 3, "C6_sleep_medication": 3, "C7_daytime_dysfunction": 3}, "details": {"bedtime": "23:00", "wake_time": "07:00", "sleep_latency_min": 5.0, "sleep_duration_hours": 8.0, "time_in_bed_hours": 8.0, "sleep_efficiency_pct": 100.0}, "clinical_flags": [{"id": "apnea_risk", "name": "\\u041f\\u043e\\u0434\\u043e\\u0437\\u0440\\u0435\\u043d\\u0438\\u0435 \\u043d\\u0430 \\u043e\\u0431\\u0441\\u0442\\u0440\\u0443\\u043a\\u0442\\u0438\\u0432\\u043d\\u043e\\u0435 \\u0430\\u043f\\u043d\\u043e\\u044d \\u0441\\u043d\\u0430", "recommendation": "\\u0420\\u0430\\u0441\\u0441\\u043c\\u043e\\u0442\\u0440\\u0435\\u0442\\u044c \\u043d\\u0430\\u043f\\u0440\\u0430\\u0432\\u043b\\u0435\\u043d\\u0438\\u0435 \\u043d\\u0430 \\u043f\\u043e\\u043b\\u0438\\u0441\\u043e\\u043c\\u043d\\u043e\\u0433\\u0440\\u0430\\u0444\\u0438\\u044e"}, {"id": "rls_risk", "name": "\\u041f\\u043e\\u0434\\u043e\\u0437\\u0440\\u0435\\u043d\\u0438\\u0435 \\u043d\\u0430 \\u0441\\u0438\\u043d\\u0434\\u0440\\u043e\\u043c \\u0431\\u0435\\u0441\\u043f\\u043e\\u043a\\u043e\\u0439\\u043d\\u044b\\u0445 \\u043d\\u043e\\u0433", "recommendation": "\\u0414\\u043e\\u043f\\u043e\\u043b\\u043d\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0439 \\u0441\\u043a\\u0440\\u0438\\u043d\\u0438\\u043d\\u0433 (\\u0448\\u043a\\u0430\\u043b\\u0430 IRLS)"}, {"id": "parasomnia_risk", "name": "\\u041f\\u043e\\u0434\\u043e\\u0437\\u0440\\u0435\\u043d\\u0438\\u0435 \\u043d\\u0430 \\u043f\\u0430\\u0440\\u0430\\u0441\\u043e\\u043c\\u043d\\u0438\\u0438", "recommendation": "\\u041a\\u043e\\u043d\\u0441\\u0443\\u043b\\u044c\\u0442\\u0430\\u0446\\u0438\\u044f \\u0441\\u043e\\u043c\\u043d\\u043e\\u043b\\u043e\\u0433\\u0430"}], "q10_partner": 3}	[{"question_id": "q1", "value": "23:00"}, {"question_id": "q2", "value": "5"}, {"question_id": "q3", "value": "07:00"}, {"question_id": "q4", "value": "8"}, {"question_id": "q5a", "value": 3}, {"question_id": "q5b", "value": 3}, {"question_id": "q5c", "value": 3}, {"question_id": "q5d", "value": 3}, {"question_id": "q5e", "value": 3}, {"question_id": "q5f", "value": 3}, {"question_id": "q5g", "value": 3}, {"question_id": "q5h", "value": 3}, {"question_id": "q5i", "value": 3}, {"question_id": "q5j", "value": 3}, {"question_id": "q6", "value": 3}, {"question_id": "q7", "value": 3}, {"question_id": "q8", "value": 3}, {"question_id": "q9", "value": 3}, {"question_id": "q10", "value": 3}, {"question_id": "q11a", "value": 3}, {"question_id": "q11b", "value": 3}, {"question_id": "q11c", "value": 3}, {"question_id": "q11d", "value": 3}, {"question_id": "q11e", "value": 0}]	2026-02-07 17:39:42.864659+03	2026-02-07 17:39:42.864659+03
515e25a8-d0dd-426e-b9db-6adea7eb5dbf	1	PSQI	1.0	2026-02-07 17:20:40.489804+03	{"total_score": 14, "summary": "PSQI: 14 \\u0431\\u0430\\u043b\\u043b\\u043e\\u0432 \\u2014 \\u0417\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043d\\u0430\\u0440\\u0443\\u0448\\u0435\\u043d\\u0438\\u044f \\u0441\\u043d\\u0430", "level": "significant", "label": "\\u0417\\u043d\\u0430\\u0447\\u0438\\u0442\\u0435\\u043b\\u044c\\u043d\\u044b\\u0435 \\u043d\\u0430\\u0440\\u0443\\u0448\\u0435\\u043d\\u0438\\u044f \\u0441\\u043d\\u0430", "components": {"C1_subjective_quality": 3, "C2_sleep_latency": 2, "C3_sleep_duration": 0, "C4_sleep_efficiency": 0, "C5_sleep_disturbances": 3, "C6_sleep_medication": 3, "C7_daytime_dysfunction": 3}, "details": {"bedtime": "23:00", "wake_time": "07:00", "sleep_latency_min": 5.0, "sleep_duration_hours": 8.0, "time_in_bed_hours": 8.0, "sleep_efficiency_pct": 100.0}, "clinical_flags": [], "q10_partner": 0}	[{"question_id": "q1", "value": "23:00"}, {"question_id": "q2", "value": "5"}, {"question_id": "q3", "value": "07:00"}, {"question_id": "q4", "value": "8"}, {"question_id": "q5i", "value": 3}, {"question_id": "q5j", "value": 0}, {"question_id": "q5h", "value": 3}, {"question_id": "q5g", "value": 3}, {"question_id": "q5f", "value": 3}, {"question_id": "q5e", "value": 3}, {"question_id": "q5d", "value": 3}, {"question_id": "q5c", "value": 3}, {"question_id": "q5b", "value": 3}, {"question_id": "q5a", "value": 3}, {"question_id": "q6", "value": 3}, {"question_id": "q7", "value": 3}, {"question_id": "q9", "value": 3}, {"question_id": "q8", "value": 3}, {"question_id": "q10", "value": 0}]	2026-02-07 20:20:40.489231+03	2026-02-07 20:20:40.489231+03
\.


--
-- TOC entry 5096 (class 0 OID 18339)
-- Dependencies: 223
-- Data for Name: users; Type: TABLE DATA; Schema: users; Owner: postgres
--

COPY users.users (id, full_name, age, gender, consent_personal_data, consent_bot_use, telegram_id, external_ids, patient_token) FROM stdin;
1	Ѱ Dmitry Ubejkon	\N	\N	t	t	203627906	\N	q1pHYT3PKKO7sH6m1rVqkV-eqYxw6zJt
\.


--
-- TOC entry 5101 (class 0 OID 18378)
-- Dependencies: 228
-- Data for Name: bp_measurements; Type: TABLE DATA; Schema: vitals; Owner: postgres
--

COPY vitals.bp_measurements (systolic, diastolic, pulse, context, id, user_id, session_id, measured_at, created_at, updated_at) FROM stdin;
120	80	\N	pre_hd	33a8ebb9-7d72-4f9c-9e16-299d7fca2cb6	1	\N	2025-11-26 15:24:47.424644+03	2025-11-26 15:24:47.427249+03	2025-11-26 15:24:47.427249+03
130	90	\N	pre_hd	ad48a921-27b9-4e3b-b691-8d191c2caba5	1	\N	2025-11-26 16:05:57.188216+03	2025-11-26 16:05:57.190675+03	2025-11-26 16:05:57.190675+03
130	80	\N	home	73a89906-4ed2-42da-829b-325c8a910ac0	1	\N	2025-11-26 16:16:11.417325+03	2025-11-26 16:16:11.415992+03	2025-11-26 16:16:11.415992+03
110	60	70	na	306d3a76-fbc9-4cd5-9642-b49be40af3cb	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 10:24:28.352+03	2025-11-27 10:25:09.520731+03	2025-11-27 10:25:09.520731+03
190	120	\N	na	751f0101-3461-43bf-8d02-6070b9668375	1	\N	2025-11-27 18:02:33.561+03	2025-11-27 18:02:33.571212+03	2025-11-27 18:02:33.571212+03
130	95	99	na	2b17944a-fc19-4395-a06a-a675500f8f45	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-12-06 17:48:57.454+03	2025-12-06 17:49:59.420182+03	2025-12-06 17:49:59.420182+03
120	95	\N	clinic	17a9e490-e2ff-4e87-9bb6-f88af9043331	1	\N	2025-12-06 18:15:35.118+03	2025-12-06 18:15:35.12996+03	2025-12-06 18:15:35.12996+03
120	80	\N	pre_hd	3ee39860-e67c-4dce-bc2c-d8a191512b76	1	\N	2025-12-07 20:35:50.43+03	2025-12-07 20:35:50.442608+03	2025-12-07 20:35:50.442608+03
120	90	\N	home	7f00e9ba-13d7-4f4f-b7d1-e1a172c2cad4	1	\N	2025-12-08 13:32:43.692+03	2025-12-08 13:32:43.702511+03	2025-12-08 13:32:43.702511+03
150	100	\N	home	e9156a7c-1a75-4bdd-a2a6-4c40bd52c68a	1	\N	2025-12-23 01:48:41.397+03	2025-12-23 01:48:41.409781+03	2025-12-23 01:48:41.409781+03
120	80	\N	pre_hd	b6013833-c99e-45ef-97ab-8bdb3d83317c	1	\N	2026-02-06 19:58:02.594+03	2026-02-06 19:58:02.602875+03	2026-02-06 19:58:02.602875+03
\.


--
-- TOC entry 5102 (class 0 OID 18393)
-- Dependencies: 229
-- Data for Name: pulse_measurements; Type: TABLE DATA; Schema: vitals; Owner: postgres
--

COPY vitals.pulse_measurements (bpm, context, id, user_id, session_id, measured_at, created_at, updated_at) FROM stdin;
75	pre_hd	b900771b-07a2-4261-bc44-0e1748bfe583	1	\N	2025-11-26 15:24:55.612229+03	2025-11-26 15:24:55.614417+03	2025-11-26 15:24:55.614417+03
99	na	3ecb9469-0013-4e08-a573-6f8e1794425c	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 10:21:27.819+03	2025-11-27 10:38:58.314518+03	2025-11-27 10:38:58.314518+03
110	na	026ac565-8a6a-4e68-a47d-62b53e2fb9e2	1	\N	2025-11-27 18:02:41.601+03	2025-11-27 18:02:41.916172+03	2025-11-27 18:02:41.916172+03
120	na	18faf27d-a30d-4883-b0fb-f02bc2460a0a	1	\N	2025-11-27 21:33:03.877+03	2025-11-27 21:33:03.897486+03	2025-11-27 21:33:03.897486+03
99	na	65e5277a-6812-4bbb-a692-40f022e3b89c	1	\N	2025-11-27 21:33:43.348+03	2025-11-27 21:33:43.663988+03	2025-11-27 21:33:43.663988+03
99	na	13a1d345-dc6b-4ea5-b1ac-8da7e07d9548	1	\N	2025-11-27 21:34:06.517+03	2025-11-27 21:34:06.52598+03	2025-11-27 21:34:06.52598+03
99	na	654638d1-bf05-4c0b-b802-ab6e87842c9f	1	\N	2025-11-27 21:34:12.968+03	2025-11-27 21:34:13.293229+03	2025-11-27 21:34:13.293229+03
59	na	3810f330-7a6a-40cb-90b4-6065f5351fb6	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 21:43:47.525+03	2025-11-27 21:44:21.175703+03	2025-11-27 21:44:21.175703+03
99	na	4e16a8eb-ce35-42a9-a35f-d38461f60197	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:11:52.282+03	2025-11-27 23:12:59.706369+03	2025-11-27 23:12:59.706369+03
99	na	00f28d6f-66bd-4012-b830-abfd09f0daef	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:11:52.282+03	2025-11-27 23:13:04.767425+03	2025-11-27 23:13:04.767425+03
99	na	dab9b7cf-b52b-4fca-b8ea-6c2126257f8b	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:11:52.282+03	2025-11-27 23:13:56.331502+03	2025-11-27 23:13:56.331502+03
199	na	f4236fe6-a653-4361-9ac0-41d903833baa	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:11:52.282+03	2025-11-27 23:14:04.512048+03	2025-11-27 23:14:04.512048+03
80	na	6987b203-83cf-490f-b4bd-d48584bbf9ac	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:17:16.958+03	2025-11-27 23:19:22.171275+03	2025-11-27 23:19:22.171275+03
80	na	3771dfab-6ede-437e-9bc6-9478653f44be	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:17:16.958+03	2025-11-27 23:19:23.466023+03	2025-11-27 23:19:23.466023+03
80	na	08159e86-0e60-4dec-b8b8-57bdf782b369	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:17:16.958+03	2025-11-27 23:19:31.662166+03	2025-11-27 23:19:31.662166+03
81	na	fb37d86d-ed53-423e-8371-c3f467c24709	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:17:16.958+03	2025-11-27 23:22:32.589024+03	2025-11-27 23:22:32.589024+03
81	na	3fb6f7be-ca6a-4162-b00e-1c1231b6b922	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 23:23:16.958+03	2025-11-27 23:23:31.268543+03	2025-11-27 23:23:31.268543+03
99	na	2617f289-72da-47f1-9e87-ca57cc64f6f3	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-12-06 17:08:39.364+03	2025-12-06 17:09:07.403629+03	2025-12-06 17:09:07.403629+03
65	post_hd	75cb4909-8d82-4e70-bba8-dcf6c4b14dd1	1	\N	2025-12-06 18:28:04.132+03	2025-12-06 18:28:04.466436+03	2025-12-06 18:28:04.466436+03
88	pre_hd	9e56170d-5a53-45c6-aff1-56c6571f7319	1	\N	2025-12-07 20:35:54.543+03	2025-12-07 20:35:54.551941+03	2025-12-07 20:35:54.551941+03
70	home	6030d7b2-0612-49fd-85fe-3390a6e08cfc	1	\N	2025-12-08 08:21:20.501+03	2025-12-08 08:21:20.510738+03	2025-12-08 08:21:20.510738+03
100	home	c5567378-1b56-4cce-aa88-62c2a68c645d	1	\N	2025-12-23 01:48:49.973+03	2025-12-23 01:48:49.983738+03	2025-12-23 01:48:49.983738+03
60	na	e5fa7cbf-0860-4f80-8cde-4ddefcb6a3e2	1	\N	2026-02-06 20:03:36.249+03	2026-02-06 20:03:36.26084+03	2026-02-06 20:03:36.26084+03
120	na	33f67839-bc96-4f1c-8499-4d0994478926	1	\N	2026-02-06 20:11:06.672+03	2026-02-06 20:11:06.679889+03	2026-02-06 20:11:06.679889+03
55	na	1f9f4864-95ba-46ac-a14f-5224462a1a53	1	\N	2026-02-06 20:11:30.473+03	2026-02-06 20:11:30.481013+03	2026-02-06 20:11:30.481013+03
\.


--
-- TOC entry 5121 (class 0 OID 18682)
-- Dependencies: 248
-- Data for Name: water_intake; Type: TABLE DATA; Schema: vitals; Owner: postgres
--

COPY vitals.water_intake (id, user_id, session_id, measured_at, created_at, updated_at, volume_ml, liquid_type, context) FROM stdin;
53332606-c709-45c0-80cc-bfd1afafa2f0	1	\N	2026-02-06 21:18:39.703+03	2026-02-06 21:18:39.72896+03	2026-02-06 21:18:39.72896+03	100	\N	na
7c9c76fd-bf6b-416d-90eb-07766f0810b1	1	\N	2026-02-06 21:18:51.559+03	2026-02-06 21:18:51.567516+03	2026-02-06 21:18:51.567516+03	250	\N	na
6e314cd0-1d9d-40c7-8298-5a45a697e292	1	\N	2026-02-06 21:22:22.747+03	2026-02-06 21:22:22.757283+03	2026-02-06 21:22:22.757283+03	500	\N	na
5857d492-c7d6-4310-b5d1-a1bd965db8e3	1	\N	2026-02-06 21:22:36.03+03	2026-02-06 21:22:36.038696+03	2026-02-06 21:22:36.038696+03	100	\N	na
50b28276-0d89-4b90-9481-353ecc580207	1	\N	2026-02-06 21:28:26.356+03	2026-02-06 21:28:26.365081+03	2026-02-06 21:28:26.365081+03	100	\N	na
\.


--
-- TOC entry 5103 (class 0 OID 18408)
-- Dependencies: 230
-- Data for Name: weight_measurements; Type: TABLE DATA; Schema: vitals; Owner: postgres
--

COPY vitals.weight_measurements (weight, context, id, user_id, session_id, measured_at, created_at, updated_at) FROM stdin;
93.50	home_evening	0e157119-49ea-4a75-92c5-7d3af550fbe3	1	\N	2025-11-26 15:25:05.083012+03	2025-11-26 15:25:05.085158+03	2025-11-26 15:25:05.085158+03
96.00	na	160f4e27-7926-40fb-9d29-57deea84a521	1	\N	2025-11-26 16:06:07.666944+03	2025-11-26 16:06:07.6687+03	2025-11-26 16:06:07.6687+03
63.00	home_morning	dcac24b5-bf0a-4ab0-bb32-d5b61830cbbb	1	\N	2025-11-26 16:15:59.879087+03	2025-11-26 16:15:59.874978+03	2025-11-26 16:15:59.874978+03
90.00	na	b1aae39a-6200-444b-bf90-51e66b7d44b9	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-26 22:32:47.88+03	2025-11-26 22:33:02.216706+03	2025-11-26 22:33:02.216706+03
101.00	na	e44c439e-bcc8-4973-9840-cecfa016d64a	1	3fa85f64-5717-4562-b3fc-2c963f66afa6	2025-11-27 10:39:25.672+03	2025-11-27 10:39:32.004267+03	2025-11-27 10:39:32.004267+03
150.00	na	7ba3413c-b3db-488f-a865-354af9503f2a	1	\N	2025-11-27 18:02:52.829+03	2025-11-27 18:02:52.839993+03	2025-11-27 18:02:52.839993+03
101.00	home_evening	41046881-fa4a-408a-8cb6-27a028012eec	1	\N	2025-11-28 09:57:57.868+03	2025-11-28 09:57:57.882927+03	2025-11-28 09:57:57.882927+03
31.50	clinic	cd8909ae-42d5-4462-9a1a-4fcf2474818b	1	\N	2025-12-06 18:28:18.044+03	2025-12-06 18:28:18.054103+03	2025-12-06 18:28:18.054103+03
92.00	pre_hd	da7ae811-8146-435c-88c4-d61087cc5976	1	\N	2025-12-07 20:35:58.393+03	2025-12-07 20:35:58.401766+03	2025-12-07 20:35:58.401766+03
96.00	home	aed36955-09f5-492f-9777-4ab31b2b2545	1	\N	2025-12-08 08:22:51.661+03	2025-12-08 08:22:51.66999+03	2025-12-08 08:22:51.66999+03
95.00	pre_hd	ab2509d7-3efa-4cd6-a104-163e76786157	1	\N	2026-02-06 21:27:28.779+03	2026-02-06 21:27:28.788112+03	2026-02-06 21:27:28.788112+03
\.


--
-- TOC entry 5138 (class 0 OID 0)
-- Dependencies: 233
-- Name: lesson_cards_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.lesson_cards_id_seq', 108, true);


--
-- TOC entry 5139 (class 0 OID 0)
-- Dependencies: 239
-- Name: lesson_progress_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.lesson_progress_id_seq', 7, true);


--
-- TOC entry 5140 (class 0 OID 0)
-- Dependencies: 245
-- Name: lesson_test_questions_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.lesson_test_questions_id_seq', 90, true);


--
-- TOC entry 5141 (class 0 OID 0)
-- Dependencies: 241
-- Name: lesson_test_results_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.lesson_test_results_id_seq', 23, true);


--
-- TOC entry 5142 (class 0 OID 0)
-- Dependencies: 243
-- Name: lesson_tests_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.lesson_tests_id_seq', 29, true);


--
-- TOC entry 5143 (class 0 OID 0)
-- Dependencies: 231
-- Name: lessons_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.lessons_id_seq', 26, true);


--
-- TOC entry 5144 (class 0 OID 0)
-- Dependencies: 237
-- Name: practice_logs_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.practice_logs_id_seq', 1, false);


--
-- TOC entry 5145 (class 0 OID 0)
-- Dependencies: 235
-- Name: practices_id_seq; Type: SEQUENCE SET; Schema: education; Owner: postgres
--

SELECT pg_catalog.setval('education.practices_id_seq', 1, false);


--
-- TOC entry 5146 (class 0 OID 0)
-- Dependencies: 226
-- Name: drafts_id_seq; Type: SEQUENCE SET; Schema: scales; Owner: postgres
--

SELECT pg_catalog.setval('scales.drafts_id_seq', 1, true);


--
-- TOC entry 5147 (class 0 OID 0)
-- Dependencies: 224
-- Name: responses_id_seq; Type: SEQUENCE SET; Schema: scales; Owner: postgres
--

SELECT pg_catalog.setval('scales.responses_id_seq', 1, true);


--
-- TOC entry 5148 (class 0 OID 0)
-- Dependencies: 222
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: users; Owner: postgres
--

SELECT pg_catalog.setval('users.users_id_seq', 1, true);


--
-- TOC entry 4900 (class 2606 OID 18455)
-- Name: lesson_cards lesson_cards_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_cards
    ADD CONSTRAINT lesson_cards_pkey PRIMARY KEY (id);


--
-- TOC entry 4912 (class 2606 OID 18587)
-- Name: lesson_progress lesson_progress_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_progress
    ADD CONSTRAINT lesson_progress_pkey PRIMARY KEY (id);


--
-- TOC entry 4923 (class 2606 OID 18645)
-- Name: lesson_test_questions lesson_test_questions_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_test_questions
    ADD CONSTRAINT lesson_test_questions_pkey PRIMARY KEY (id);


--
-- TOC entry 4914 (class 2606 OID 18608)
-- Name: lesson_test_results lesson_test_results_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_test_results
    ADD CONSTRAINT lesson_test_results_pkey PRIMARY KEY (id);


--
-- TOC entry 4920 (class 2606 OID 18628)
-- Name: lesson_tests lesson_tests_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_tests
    ADD CONSTRAINT lesson_tests_pkey PRIMARY KEY (id);


--
-- TOC entry 4895 (class 2606 OID 18444)
-- Name: lessons lessons_code_key; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lessons
    ADD CONSTRAINT lessons_code_key UNIQUE (code);


--
-- TOC entry 4897 (class 2606 OID 18442)
-- Name: lessons lessons_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lessons
    ADD CONSTRAINT lessons_pkey PRIMARY KEY (id);


--
-- TOC entry 4907 (class 2606 OID 18563)
-- Name: practice_logs practice_logs_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.practice_logs
    ADD CONSTRAINT practice_logs_pkey PRIMARY KEY (id);


--
-- TOC entry 4903 (class 2606 OID 18546)
-- Name: practices practices_pkey; Type: CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.practices
    ADD CONSTRAINT practices_pkey PRIMARY KEY (id);


--
-- TOC entry 4873 (class 2606 OID 18337)
-- Name: alembic_version alembic_version_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkey PRIMARY KEY (version_num);


--
-- TOC entry 4881 (class 2606 OID 18372)
-- Name: drafts drafts_pkey; Type: CONSTRAINT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.drafts
    ADD CONSTRAINT drafts_pkey PRIMARY KEY (id);


--
-- TOC entry 4879 (class 2606 OID 18358)
-- Name: responses responses_pkey; Type: CONSTRAINT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.responses
    ADD CONSTRAINT responses_pkey PRIMARY KEY (id);


--
-- TOC entry 4929 (class 2606 OID 18673)
-- Name: scale_results scale_results_pkey; Type: CONSTRAINT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.scale_results
    ADD CONSTRAINT scale_results_pkey PRIMARY KEY (id);


--
-- TOC entry 4877 (class 2606 OID 18348)
-- Name: users users_pkey; Type: CONSTRAINT; Schema: users; Owner: postgres
--

ALTER TABLE ONLY users.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- TOC entry 4883 (class 2606 OID 18385)
-- Name: bp_measurements bp_measurements_pkey; Type: CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.bp_measurements
    ADD CONSTRAINT bp_measurements_pkey PRIMARY KEY (id);


--
-- TOC entry 4933 (class 2606 OID 18690)
-- Name: water_intake pk_water_intake; Type: CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.water_intake
    ADD CONSTRAINT pk_water_intake PRIMARY KEY (id);


--
-- TOC entry 4889 (class 2606 OID 18400)
-- Name: pulse_measurements pulse_measurements_pkey; Type: CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.pulse_measurements
    ADD CONSTRAINT pulse_measurements_pkey PRIMARY KEY (id);


--
-- TOC entry 4893 (class 2606 OID 18415)
-- Name: weight_measurements weight_measurements_pkey; Type: CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.weight_measurements
    ADD CONSTRAINT weight_measurements_pkey PRIMARY KEY (id);


--
-- TOC entry 4898 (class 1259 OID 18461)
-- Name: idx_lesson_cards_lesson_id; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX idx_lesson_cards_lesson_id ON education.lesson_cards USING btree (lesson_id);


--
-- TOC entry 4904 (class 1259 OID 18575)
-- Name: idx_practice_logs_practice_id; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX idx_practice_logs_practice_id ON education.practice_logs USING btree (practice_id);


--
-- TOC entry 4905 (class 1259 OID 18574)
-- Name: idx_practice_logs_user_id; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX idx_practice_logs_user_id ON education.practice_logs USING btree (user_id);


--
-- TOC entry 4901 (class 1259 OID 18552)
-- Name: idx_practices_lesson_id; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX idx_practices_lesson_id ON education.practices USING btree (lesson_id);


--
-- TOC entry 4908 (class 1259 OID 18595)
-- Name: lesson_progress_lesson_idx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX lesson_progress_lesson_idx ON education.lesson_progress USING btree (lesson_id);


--
-- TOC entry 4909 (class 1259 OID 18594)
-- Name: lesson_progress_patient_idx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX lesson_progress_patient_idx ON education.lesson_progress USING btree (patient_token);


--
-- TOC entry 4910 (class 1259 OID 18593)
-- Name: lesson_progress_patient_lesson_uidx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE UNIQUE INDEX lesson_progress_patient_lesson_uidx ON education.lesson_progress USING btree (patient_token, lesson_id);


--
-- TOC entry 4921 (class 1259 OID 18651)
-- Name: lesson_test_questions_order_uidx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE UNIQUE INDEX lesson_test_questions_order_uidx ON education.lesson_test_questions USING btree (test_id, order_index);


--
-- TOC entry 4924 (class 1259 OID 18652)
-- Name: lesson_test_questions_test_idx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX lesson_test_questions_test_idx ON education.lesson_test_questions USING btree (test_id);


--
-- TOC entry 4915 (class 1259 OID 18614)
-- Name: lesson_test_results_quiz_token_idx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX lesson_test_results_quiz_token_idx ON education.lesson_test_results USING btree (test_id, patient_token, created_at DESC);


--
-- TOC entry 4916 (class 1259 OID 18615)
-- Name: lesson_test_results_token_idx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX lesson_test_results_token_idx ON education.lesson_test_results USING btree (patient_token);


--
-- TOC entry 4917 (class 1259 OID 18634)
-- Name: lesson_tests_code_uidx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE UNIQUE INDEX lesson_tests_code_uidx ON education.lesson_tests USING btree (code);


--
-- TOC entry 4918 (class 1259 OID 18635)
-- Name: lesson_tests_lesson_idx; Type: INDEX; Schema: education; Owner: postgres
--

CREATE INDEX lesson_tests_lesson_idx ON education.lesson_tests USING btree (lesson_id);


--
-- TOC entry 4925 (class 1259 OID 18681)
-- Name: ix_scale_results_measured_at; Type: INDEX; Schema: scales; Owner: postgres
--

CREATE INDEX ix_scale_results_measured_at ON scales.scale_results USING btree (measured_at);


--
-- TOC entry 4926 (class 1259 OID 18680)
-- Name: ix_scale_results_scale_code; Type: INDEX; Schema: scales; Owner: postgres
--

CREATE INDEX ix_scale_results_scale_code ON scales.scale_results USING btree (scale_code);


--
-- TOC entry 4927 (class 1259 OID 18679)
-- Name: ix_scale_results_user_id; Type: INDEX; Schema: scales; Owner: postgres
--

CREATE INDEX ix_scale_results_user_id ON scales.scale_results USING btree (user_id);


--
-- TOC entry 4874 (class 1259 OID 18428)
-- Name: ix_users_patient_token; Type: INDEX; Schema: users; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_patient_token ON users.users USING btree (patient_token);


--
-- TOC entry 4875 (class 1259 OID 18349)
-- Name: ix_users_users_telegram_id; Type: INDEX; Schema: users; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_users_telegram_id ON users.users USING btree (telegram_id);


--
-- TOC entry 4884 (class 1259 OID 18391)
-- Name: ix_bp_measurements_measured_at; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_bp_measurements_measured_at ON vitals.bp_measurements USING btree (measured_at);


--
-- TOC entry 4885 (class 1259 OID 18392)
-- Name: ix_bp_measurements_session_id; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_bp_measurements_session_id ON vitals.bp_measurements USING btree (session_id);


--
-- TOC entry 4886 (class 1259 OID 18406)
-- Name: ix_pulse_measurements_measured_at; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_pulse_measurements_measured_at ON vitals.pulse_measurements USING btree (measured_at);


--
-- TOC entry 4887 (class 1259 OID 18407)
-- Name: ix_pulse_measurements_session_id; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_pulse_measurements_session_id ON vitals.pulse_measurements USING btree (session_id);


--
-- TOC entry 4930 (class 1259 OID 18697)
-- Name: ix_water_intake_measured_at; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_water_intake_measured_at ON vitals.water_intake USING btree (measured_at);


--
-- TOC entry 4931 (class 1259 OID 18696)
-- Name: ix_water_intake_session_id; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_water_intake_session_id ON vitals.water_intake USING btree (session_id);


--
-- TOC entry 4890 (class 1259 OID 18421)
-- Name: ix_weight_measurements_measured_at; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_weight_measurements_measured_at ON vitals.weight_measurements USING btree (measured_at);


--
-- TOC entry 4891 (class 1259 OID 18422)
-- Name: ix_weight_measurements_session_id; Type: INDEX; Schema: vitals; Owner: postgres
--

CREATE INDEX ix_weight_measurements_session_id ON vitals.weight_measurements USING btree (session_id);


--
-- TOC entry 4939 (class 2606 OID 18456)
-- Name: lesson_cards lesson_cards_lesson_id_fkey; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_cards
    ADD CONSTRAINT lesson_cards_lesson_id_fkey FOREIGN KEY (lesson_id) REFERENCES education.lessons(id) ON DELETE CASCADE;


--
-- TOC entry 4943 (class 2606 OID 18588)
-- Name: lesson_progress lesson_progress_lesson_fk; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_progress
    ADD CONSTRAINT lesson_progress_lesson_fk FOREIGN KEY (lesson_id) REFERENCES education.lessons(id) ON DELETE CASCADE;


--
-- TOC entry 4946 (class 2606 OID 18646)
-- Name: lesson_test_questions lesson_test_questions_test_fk; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_test_questions
    ADD CONSTRAINT lesson_test_questions_test_fk FOREIGN KEY (test_id) REFERENCES education.lesson_tests(id) ON DELETE CASCADE;


--
-- TOC entry 4944 (class 2606 OID 18653)
-- Name: lesson_test_results lesson_test_results_test_fk; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_test_results
    ADD CONSTRAINT lesson_test_results_test_fk FOREIGN KEY (test_id) REFERENCES education.lesson_tests(id) ON DELETE CASCADE;


--
-- TOC entry 4945 (class 2606 OID 18629)
-- Name: lesson_tests lesson_tests_lesson_fk; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.lesson_tests
    ADD CONSTRAINT lesson_tests_lesson_fk FOREIGN KEY (lesson_id) REFERENCES education.lessons(id) ON DELETE CASCADE;


--
-- TOC entry 4941 (class 2606 OID 18569)
-- Name: practice_logs practice_logs_practice_id_fkey; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.practice_logs
    ADD CONSTRAINT practice_logs_practice_id_fkey FOREIGN KEY (practice_id) REFERENCES education.practices(id) ON DELETE CASCADE;


--
-- TOC entry 4942 (class 2606 OID 18564)
-- Name: practice_logs practice_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.practice_logs
    ADD CONSTRAINT practice_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(id) ON DELETE CASCADE;


--
-- TOC entry 4940 (class 2606 OID 18547)
-- Name: practices practices_lesson_id_fkey; Type: FK CONSTRAINT; Schema: education; Owner: postgres
--

ALTER TABLE ONLY education.practices
    ADD CONSTRAINT practices_lesson_id_fkey FOREIGN KEY (lesson_id) REFERENCES education.lessons(id) ON DELETE CASCADE;


--
-- TOC entry 4935 (class 2606 OID 18373)
-- Name: drafts drafts_user_id_fkey; Type: FK CONSTRAINT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.drafts
    ADD CONSTRAINT drafts_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(id);


--
-- TOC entry 4934 (class 2606 OID 18359)
-- Name: responses responses_user_id_fkey; Type: FK CONSTRAINT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.responses
    ADD CONSTRAINT responses_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(id);


--
-- TOC entry 4947 (class 2606 OID 18674)
-- Name: scale_results scale_results_user_id_fkey; Type: FK CONSTRAINT; Schema: scales; Owner: postgres
--

ALTER TABLE ONLY scales.scale_results
    ADD CONSTRAINT scale_results_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(id) ON DELETE CASCADE;


--
-- TOC entry 4936 (class 2606 OID 18386)
-- Name: bp_measurements bp_measurements_user_id_fkey; Type: FK CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.bp_measurements
    ADD CONSTRAINT bp_measurements_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(id);


--
-- TOC entry 4948 (class 2606 OID 18691)
-- Name: water_intake fk_water_intake_user_id_users; Type: FK CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.water_intake
    ADD CONSTRAINT fk_water_intake_user_id_users FOREIGN KEY (user_id) REFERENCES users.users(id);


--
-- TOC entry 4937 (class 2606 OID 18401)
-- Name: pulse_measurements pulse_measurements_user_id_fkey; Type: FK CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.pulse_measurements
    ADD CONSTRAINT pulse_measurements_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(id);


--
-- TOC entry 4938 (class 2606 OID 18416)
-- Name: weight_measurements weight_measurements_user_id_fkey; Type: FK CONSTRAINT; Schema: vitals; Owner: postgres
--

ALTER TABLE ONLY vitals.weight_measurements
    ADD CONSTRAINT weight_measurements_user_id_fkey FOREIGN KEY (user_id) REFERENCES users.users(id);


-- Completed on 2026-02-07 20:58:56

--
-- PostgreSQL database dump complete
--

