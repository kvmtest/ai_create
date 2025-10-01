-- AI CREAT: Database Schema
-- Target RDBMS: PostgreSQL
--

-- Use an ENUM type for user roles for data integrity
CREATE TYPE user_role AS ENUM ('user', 'admin');

-- Use ENUM types for statuses to prevent invalid states
CREATE TYPE project_status AS ENUM ('uploading', 'processing', 'ready_for_review', 'generating', 'completed', 'failed');
CREATE TYPE job_status AS ENUM ('pending', 'processing', 'completed', 'failed');
CREATE TYPE format_type AS ENUM ('resizing', 'repurposing');

-- Table: users
-- Stores user accounts, credentials, and preferences.
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL,
    role user_role NOT NULL DEFAULT 'user',
    preferences JSONB DEFAULT '{}', -- e.g., { "theme": "dark" }
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: projects
-- Represents a batch of uploaded assets.
CREATE TABLE projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    status project_status NOT NULL DEFAULT 'uploading',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: assets
-- Stores information about the original files uploaded by the user.
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    original_filename VARCHAR(255) NOT NULL,
    storage_path TEXT NOT NULL, -- e.g., S3 key
    file_type VARCHAR(10) NOT NULL,
    file_size_bytes BIGINT NOT NULL,
    dimensions JSONB, -- e.g., { "width": 1920, "height": 1080 }
    dpi INT,
    ai_metadata JSONB, -- For detected elements like { "product": [...], "text": [...] }
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: generation_jobs
-- Tracks the status of an AI generation request.
CREATE TABLE generation_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status job_status NOT NULL DEFAULT 'pending',
    progress INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: platforms
-- Stores the platforms for repurposing (e.g., Instagram, Acme Platform).
CREATE TABLE platforms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_by_admin_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: asset_formats
-- MERGED TABLE: Stores predefined and custom formats for both resizing and repurposing.
CREATE TABLE asset_formats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    platform_id UUID REFERENCES repurposing_platforms(id) ON DELETE CASCADE, -- Nullable, only for 'repurposing' type
    width INT NOT NULL,
    height INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_by_admin_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: generated_assets
-- Stores the output assets created by the AI generation process.
CREATE TABLE generated_assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES generation_jobs(id) ON DELETE CASCADE,
    original_asset_id UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    asset_format_id UUID REFERENCES asset_formats(id) ON DELETE SET NULL, -- Single FK to the merged formats table
    storage_path TEXT NOT NULL,
    file_type VARCHAR(10) NOT NULL,
    dimensions JSONB NOT NULL,
    is_nsfw BOOLEAN DEFAULT FALSE,
    -- JSONB to store current state of manual edits, allowing for re-editing.
    -- Example: { "crop": {"x":0,"y":0,"w":1080,"h":1080}, "saturation": 1.1, "textOverlays": [...] }
    manual_edits JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: text_style_sets
-- Stores admin-defined text style groups (e.g., Title, Subtitle, Content).
CREATE TABLE text_style_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) UNIQUE NOT NULL,
    styles JSONB NOT NULL, -- e.g., { "title": { "font": "Inter", "size": 48 }, "subtitle": { ... } }
    is_active BOOLEAN DEFAULT TRUE,
    created_by_admin_id UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table: app_settings
-- A flexible key-value store for all admin-configurable rules.
CREATE TABLE app_settings (
    id SERIAL PRIMARY KEY,
    rule_key VARCHAR(255) UNIQUE NOT NULL,
    rule_value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- Indexes for performance on frequently queried columns
CREATE INDEX idx_projects_user_id ON projects(user_id);
CREATE INDEX idx_assets_project_id ON assets(project_id);
CREATE INDEX idx_generated_assets_job_id ON generated_assets(job_id);
CREATE INDEX idx_asset_formats_type ON asset_formats(type);
