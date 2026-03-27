# ModelMesh VS Code Extension

Intelligent AI gateway integration for VS Code.

## Features

- **Send Selection to ModelMesh** - Highlight code/text and send to your configured persona
- **Persona Selection** - Choose which persona to use for requests
- **Conversation Continuity** - Responses maintain context across requests
- **Streaming Responses** - Real-time token-by-token output

## Usage

1. **Select text** in your editor
2. Press `Ctrl+Shift+P` (Cmd+Shift+P on Mac)
3. Type "ModelMesh: Ask Selected Text"
4. View response in the ModelMesh output panel

## Commands

- `ModelMesh: Ask Selected Text` - Send selected text to ModelMesh
- `ModelMesh: New Conversation` - Start a fresh conversation (clear memory)
- `ModelMesh: Select Persona` - Choose which persona to use

## Configuration

Open VS Code settings and search for "ModelMesh":

| Setting | Description | Default |
|---------|-------------|---------|
| `modelmesh.apiUrl` | ModelMesh API URL | `http://localhost:18800/v1` |
| `modelmesh.apiKey` | API key for authentication | `modelmesh_local_dev_key` |
| `modelmesh.defaultPersona` | Default persona name | `quick-helper` |
| `modelmesh.streamResponses` | Stream responses in real-time | `true` |
| `modelmesh.showCostInResponse` | Show estimated cost | `true` |

## Requirements

- ModelMesh backend running at the configured API URL
- Valid API key if authentication is enabled

## License

MIT