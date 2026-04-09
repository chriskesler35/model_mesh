# VS Code Extension Architecture

VS Code extension for DevForgeAI integration.

## Stack

- TypeScript 5.3
- VS Code API ^1.85.0
- No runtime dependencies

## Architecture Pattern

Command-based extension with TreeView provider.

## Entry Point

`extension.ts` registers 4 commands and 1 TreeView.

## Structure

### commands/sendSelection.ts

Sends selected text to ModelMesh via the chat API. Shows results in an Output Channel. Supports streaming responses.

### commands/newConversation.ts

Resets the conversation. Has a structural bug: each call creates a new client instance.

### providers/personaProvider.ts

`TreeDataProvider` for the persona list. Uses module-level `currentPersona` state.

### api/client.ts

`ModelMeshClient` class providing:
- `chat()` -- standard request/response
- `streamChat()` -- async generator over SSE
- `getPersonas()` -- fetch persona list
- `newConversation()` -- reset conversation state

### utils/config.ts

Reads VS Code settings:
- `apiUrl`
- `apiKey`
- `defaultPersona`
- `streamResponses`
- `showCostInResponse`

## API Endpoints Called

- `POST /v1/chat/completions`
- `GET /v1/personas`

## Known Issues

1. **Persona selection bug**: `sendSelection.ts` has its own `currentPersona` that never gets updated. The persona selected in the TreeView is never used in API calls.

2. **Conversation continuity broken**: A new `ModelMeshClient` is created per invocation, so `conversationId` is always null. Messages are never linked into a continuous conversation.

3. **Missing viewsContainers in package.json**: The TreeView has no sidebar location registered, so it never appears in the VS Code sidebar.

4. **refreshPersonas command not in package.json**: The command is implemented but not declared in the extension manifest, making it invisible in the Command Palette.

5. **Cost display is placeholder only**: The cost display feature reads the setting but does not render actual cost data from the API response.

## Build

- Compiler: `tsc` -> `dist/`
- Source maps enabled
- Module format: CommonJS
