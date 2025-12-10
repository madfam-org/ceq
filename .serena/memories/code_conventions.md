# CEQ Code Conventions

## Python (API + Workers)

### Style
- Python 3.11+
- Line length: 100 characters
- Linter: ruff
- Type checker: mypy (strict mode)
- Formatter: ruff format

### Patterns
```python
# FastAPI patterns
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/v1/workflows", tags=["workflows"])

class WorkflowCreate(BaseModel):
    name: str
    workflow_json: dict

@router.post("/")
async def create_workflow(data: WorkflowCreate, user: User = Depends(get_current_user)):
    ...
```

### Ruff Rules
- E, F: Pyflakes/pycodestyle errors
- I: isort imports
- N: pep8 naming
- W: warnings
- UP: pyupgrade
- B: bugbear
- C4: comprehensions
- SIM: simplify

## TypeScript (Studio)

### Style
- TypeScript 5.6+
- Next.js 14 App Router
- ESLint with next config
- Tailwind CSS + shadcn/ui

### Patterns
```typescript
// Next.js 14 app router patterns
// File: apps/studio/app/workflows/page.tsx
import { WorkflowList } from '@/components/workflow-list';
import { getWorkflows } from '@/lib/api';

export default async function WorkflowsPage() {
  const workflows = await getWorkflows();
  return <WorkflowList workflows={workflows} />;
}
```

### UI Components
- Radix UI primitives via shadcn/ui
- TanStack Query for data fetching
- Zustand for state management
- Sonner for toasts

## UI Design Principles

- **Dark mode only**: No light mode toggle
- **Keyboard-first**: All primary actions have shortcuts
- **Terminal aesthetic**: Monospace fonts, minimal chrome

## Brand Voice in Code

```typescript
// Loading states
const LOADING_MESSAGES = [
  "Quantizing entropy...",
  "Traversing latent space...",
  "Distilling chaos...",
];

// Success states  
const SUCCESS_MESSAGES = [
  "Signal acquired. 📡",
  "Materialized. ✨",
  "Entropy contained.",
];

// Error states
const ERROR_MESSAGES = [
  "Chaos won this round. Retry? [↻]",
  "Latent space turbulence detected.",
  "Signal lost in the noise.",
];
```
