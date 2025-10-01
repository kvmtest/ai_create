# Implementation Notes for AI CREAT

This document provides an overview of the proposed architecture, technology stack, and key implementation strategies for the AI CREAT platform.

## 1. Architecture Overview

We propose a **Microservices Architecture** to ensure scalability, resilience, and maintainability. The system is decoupled into logical components, each responsible for a specific domain.

*   **API Gateway:** A single entry point for all client requests. It will handle critical cross-cutting concerns such as **Authentication (JWT validation)**, request routing, and rate limiting. This keeps the downstream services clean and focused on their business logic.

*   **Core Service:** This is the primary backend service that manages users, projects, assets, and administrative rules. It handles all standard CRUD operations and orchestrates the initial steps of the generation workflow.

*   **Generation Service:** A dedicated, asynchronous service responsible for all heavy computational tasks. This includes AI analysis of uploaded assets, image resizing, repurposing, and applying manual edits. By isolating this workload, we ensure that long-running tasks do not block the main API, providing a responsive user experience.

*   **Asynchronous Workflow with a Message Queue:** The interaction between the Core Service and the Generation Service is fully asynchronous, orchestrated by a message queue (e.g., RabbitMQ).
    1.  When a user uploads files via the `POST /projects/upload` endpoint, the Core Service creates a new `Project` record, validates the request, and publishes a `project.assets_uploaded` event to the message queue.
    2.  The API immediately responds to the client with a `202 Accepted` status and a `projectId`.
    3.  The client's UI then begins polling a status endpoint (`/projects/{projectId}/status`).
    4.  One or more workers in the Generation Service consume the message, perform the initial AI analysis on the assets, update the project status in the database, and store metadata.
    5.  This decoupled, event-driven approach allows the Generation Service to be scaled independently to handle fluctuating loads without impacting the core application's performance.

### 1.1. Asynchronous Workflow & Advanced Queuing
...The client then begins polling a status endpoint...
To enhance resilience and control, we will implement a multi-queue strategy:
- **Primary Queue:** For standard user-submitted generation jobs.
- **Priority Queue:** For high-priority tasks, such as admin-initiated regenerations or premium user jobs.
- **Dead-Letter Queue (DLQ):** To automatically capture jobs that fail repeatedly, allowing for manual inspection without losing data or blocking the main queue.
The number of Generation Service workers will autoscale based on metrics like queue length and processing time to ensure cost-efficiency and performance.


## 2. Technology Stack Choices

Our proposed stack is modern, scalable, and leverages industry best practices for cloud-native applications.

*   **Backend Framework:** **Python 3 with FastAPI**. FastAPI is the ideal choice for this project. Its high performance is well-suited for I/O-bound operations like handling API requests and communicating with a message queue. Crucially, its native support for Pydantic data models allows for automatic generation of OpenAPI specifications, which directly streamlines the creation of the required deliverables and ensures the API documentation is always in sync with the code.
*   **Database:** **PostgreSQL**. Chosen for its reliability, transactional integrity, and powerful support for `JSONB` data types. The `JSONB` type is ideal for storing flexible, semi-structured data like AI metadata, user preferences, and manual edit parameters without sacrificing query performance.
*   **Message Queue:** **RabbitMQ**. A mature and highly reliable message broker that is perfect for managing the asynchronous communication between our microservices.
*   **File Storage:** **Amazon S3 (or any S3-compatible object storage)**. This provides a virtually infinitely scalable, durable, and cost-effective solution for storing user-uploaded assets and AI-generated content.
*   **Caching:** **Redis**. To be used for caching frequently accessed data, such as admin-configured rules and platform templates, reducing database load and improving API response times.

## 3. AI/LLM Integration Strategy
To ensure flexibility and avoid vendor lock-in, the system will feature a provider-agnostic AI integration layer. This will be achieved using a **Strategy or Adapter design pattern**. A configuration file will define the available providers (e.g., OpenAI, Google Gemini, Anthropic), but the core application code will interact with a standardized interface. This allows the business to switch or add new AI providers with minimal code changes.

The AI processing pipeline will consist of several key stages:
1.  **Image Analysis:** Initial detection of key elements (faces, products, text).
2.  **Element Classification:** Ranking elements based on admin-defined rules (e.g., face-centric vs. product-centric).
3.  **Adaptation Logic:** Applying adaptation strategies (Crop, Extend Canvas) based on the target format and classified elements.
4.  **Content Moderation:** Running a check for NSFW content.

## 4. Multi-Tenancy Architecture
The platform is designed to be multi-tenant to support multiple, isolated client organizations. This is achieved by introducing an `organization_id` to key data models (`users`, `projects`, `text_styles`, etc.). All data access is strictly scoped by this ID at the application layer, guaranteeing that one organization's assets and rules are completely invisible to others.

## 5. Error Handling & Retry Strategy
A robust error handling strategy is critical for a distributed system.
-   **API Errors:** The API will use standard HTTP status codes to differentiate between client errors (4xx) and server errors (5xx). Validation failures will return a `422 Unprocessable Entity` status with a detailed breakdown of the errors.
-   **Asynchronous Retries:** For transient failures during background processing (e.g., temporary network issue with an AI provider), workers will employ an **exponential backoff** retry policy (e.g., retrying after 2s, 4s, 8s). After a set number of failed attempts, the job will be moved to the Dead-Letter Queue.


## 6. Key Implementation Details

*   **Authentication & Authorization:**
    *   **JWT (JSON Web Tokens):** The `/auth/login` endpoint will issue a signed JWT. This token will be sent in the `Authorization: Bearer <token>` header on all subsequent requests.
    *   **Role-Based Access Control (RBAC):** A middleware on the API Gateway or within the Core Service will inspect the JWT payload for the user's role (`user` or `admin`) and protect admin-only endpoints from unauthorized access.

*   **Secure File Handling:**
    *   All file uploads and downloads will be handled using **pre-signed URLs**. When a user wants to upload a file, the API will provide a temporary, secure URL to which the client can directly upload the file to S3. Similarly, for downloads, a pre-signed URL provides time-limited read access. This approach is highly secure as it prevents direct exposure of storage credentials to the client.

*   **Scalability & Performance:**
    *   The services will be containerized using **Docker**, allowing for consistent deployment across environments.
    *   An orchestrator like **Kubernetes** or **Amazon ECS** will be used to manage and automatically scale the services. The number of Generation Service workers can be dynamically adjusted based on the length of the message queue to handle spikes in demand efficiently.

*   **Content Moderation (NSFW):**
    *   The NSFW detection will be a step within the Generation Service's processing pipeline. When an asset is generated, it is passed through a detection model. If flagged, the `is_nsfw` boolean is set to `true` in the `generated_assets` table. The frontend API (`/generate/{jobId}/results`) will return this flag, allowing the UI to display the appropriate warning without exposing the content directly.

*   **Consolidated Asset Formats:**
    *   Based on feedback, the concepts of "Resizing Templates" and "Repurposing Formats" have been merged into a single entity: `AssetFormat`. A `type` field (`resizing` or `repurposing`) and a nullable `platform_id` will differentiate them within a single database table and a unified set of admin API endpoints (`/admin/formats`). This simplifies management and reduces code duplication.

*   **Manual Edit Storage:**
    *   To allow users to modify previous manual edits, all edit information will be stored in a structured `manual_edits` `JSONB` column in the `generated_assets` table. Instead of creating numerous side-tables, we will enforce a clear schema on this JSON object (e.g., `{ "crop": {...}, "saturation": 0.85, "textOverlays": [...] }`). This provides the necessary structure and editability while maintaining schema flexibility.

*   **Text Style Sets:**
    *   To better align with the UI, individual text styles are now grouped into "Text Style Sets." An admin will define a set containing styles for a Title, Subtitle, and Content body. This is reflected in the `text_style_sets` database table and managed via the `/admin/text-style-sets` API endpoint.