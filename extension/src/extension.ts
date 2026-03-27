import * as vscode from 'vscode';
import { sendSelection } from './commands/sendSelection';
import { newConversation } from './commands/newConversation';
import { PersonaProvider, setCurrentPersona } from './providers/personaProvider';
import { getConfig } from './utils/config';
import { ModelMeshClient } from './api/client';

export function activate(context: vscode.ExtensionContext) {
  console.log('ModelMesh extension activated');

  // Register persona tree view
  const personaProvider = new PersonaProvider();
  const treeView = vscode.window.createTreeView('modelmesh-personas', {
    treeDataProvider: personaProvider,
    showCollapseAll: false
  });

  // Register commands
  const sendSelectionCmd = vscode.commands.registerCommand(
    'modelmesh.sendSelection',
    () => sendSelection(context)
  );

  const newConversationCmd = vscode.commands.registerCommand(
    'modelmesh.newConversation',
    () => newConversation()
  );

  const selectPersonaCmd = vscode.commands.registerCommand(
    'modelmesh.selectPersona',
    async () => {
      const client = new ModelMeshClient();
      const personas = await client.getPersonas();
      
      const selected = await vscode.window.showQuickPick(
        personas.map(p => ({ label: p.name, id: p.id })),
        { placeHolder: 'Select a persona' }
      );
      
      if (selected) {
        setCurrentPersona(selected.label);
        vscode.window.showInformationMessage(`ModelMesh: Using persona "${selected.label}"`);
      }
    }
  );

  const refreshPersonasCmd = vscode.commands.registerCommand(
    'modelmesh.refreshPersonas',
    () => personaProvider.refresh()
  );

  context.subscriptions.push(
    sendSelectionCmd,
    newConversationCmd,
    selectPersonaCmd,
    refreshPersonasCmd,
    treeView
  );
}

export function deactivate() {
  console.log('ModelMesh extension deactivated');
}