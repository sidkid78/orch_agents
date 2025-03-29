# MAAS Middleware - AI Agent Orchestration Layer

This repository contains the middleware component for the Multi-Agent Acquisition System (MAAS), which orchestrates AI agents for evaluating procurement proposals.

## Architecture Overview

The middleware acts as an orchestration layer for multiple specialized AI agents:

1. **Compliance Agent**: Evaluates proposals for regulatory compliance
2. **Evaluation Agent**: Assesses the quality and value of proposals
3. **Market Research Agent**: Provides market context and competitive analysis
4. **Orchestrator Agent**: Synthesizes insights from the specialized agents to provide a final recommendation

## Key Components

### Orchestrator

The orchestrator coordinates the execution of multiple agents and manages workflows. It includes:

- **Workflow Management**: Determines the appropriate workflow based on proposal characteristics
- **Parallel Execution**: Runs agents in parallel when possible for efficiency
- **Result Aggregation**: Combines outputs from multiple agents
- **Error Handling**: Manages failures and provides appropriate fallbacks

### Agents

Each agent is specialized for a specific aspect of proposal evaluation:

- **Compliance Agent**: Evaluates regulatory requirements, excluded parties, and contract thresholds
- **Evaluation Agent**: Scores proposals based on technical approach, past performance, and cost reasonableness
- **Market Agent**: Analyses competitive landscape, pricing, and market trends
- **Orchestrator Agent**: Synthesizes insights and provides final recommendations

### API Layer

The middleware exposes RESTful APIs for:

- Submitting proposals for evaluation
- Checking workflow status
- Retrieving evaluation results
- Providing human feedback on agent outputs

## Project Structure

```
orch_agents/
├── backend/
│   ├── azure_agents/        # Azure-specific agent implementations
│   ├── orchestrator/        # Core orchestration functionality
│   ├── tests/               # Test modules
│   ├── utils/               # Utility modules
│   ├── main.py              # FastAPI application entry point
│   └── .env                 # Environment variables (not in version control)
├── frontend/                # Frontend application (React)
│   ├── src/
│   ├── public/
│   └── package.json
├── package.json             # Project configuration
└── README.md                # Project documentation
```

## Getting Started

### Prerequisites

- Python 3.9+
- Node.js 16+
- Azure OpenAI API access
- Poetry (Python dependency management)

### Installation

1. Clone the repository:
   ```
   git clone https://github.com/your-org/orch_agents.git
   cd orch_agents
   ```

2. Install backend dependencies:
   ```
   cd backend
   poetry install
   ```

3. Install frontend dependencies:
   ```
   cd ../frontend
   npm install
   ```

4. Create a `.env` file in the backend directory:
   ```
   AZURE_OPENAI_API_KEY=your-azure-openai-api-key
   AZURE_OPENAI_ENDPOINT=your-azure-openai-endpoint
   AZURE_OPENAI_API_VERSION=2024-02-15-preview
   AZURE_COMPLIANCE_DEPLOYMENT=gpt-4o
   AZURE_EVALUATION_DEPLOYMENT=gpt-4o
   AZURE_MARKET_DEPLOYMENT=gpt-4o
   AZURE_ORCHESTRATOR_DEPLOYMENT=gpt-4o
   ```

### Running the Application

1. Start the backend server:
   ```
   cd backend
   poetry run python main.py
   ```

2. Start the frontend development server:
   ```
   cd frontend
   npm start
   ```

## API Documentation

The API is documented using OpenAPI/Swagger and is available at `/docs` when the backend server is running.

### Key Endpoints

- `POST /api/evaluate-proposal`: Submit a proposal for evaluation
- `POST /api/orchestrator/workflows`: Start a new workflow
- `GET /api/orchestrator/workflows/{workflow_id}`: Get workflow status
- `GET /api/orchestrator/workflows/{workflow_id}/result`: Get workflow results
- `POST /api/human-feedback`: Submit feedback on agent outputs

## Testing

Run tests with:

```
cd backend
poetry run pytest
```

## Contributing

Please read the [CONTRIBUTING.md](CONTRIBUTING.md) file for details on our code of conduct and the process for submitting pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.