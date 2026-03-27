import * as vscode from 'vscode';
import { ModelMeshClient } from '../api/client';
import { getConfig } from '../utils/config';

let currentPersona: string | undefined;

export async function sendSelection(context: vscode.ExtensionContext) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showErrorMessage('No active editor');
    return;
  }

  const selection = editor.selection;
  const selectedText = editor.document.getText(selection);
  
  if (!selectedText) {
    vscode.window.showErrorMessage('No text selected');
    return;
  }

  const config = getConfig();
  const client = new ModelMeshClient();
  
  // Use stored persona or default
  const persona = currentPersona || config.defaultPersona;
  
  // Create or get output channel
  const outputChannel = vscode.window.createOutputChannel('ModelMesh');
  outputChannel.show(true);
  outputChannel.appendLine(`\n--- Sending to ${persona} ---\n`);
  outputChannel.appendLine(`Input:\n${selectedText}\n`);
  outputChannel.appendLine('--- Response ---\n');

  try {
    if (config.streamResponses) {
      // Stream response
      for await (const chunk of client.streamChat([{ role: 'user', content: selectedText }], persona)) {
        outputChannel.append(chunk);
      }
    } else {
      // Non-streaming response
      const response = await client.chat([{ role: 'user', content: selectedText }], persona);
      outputChannel.appendLine(response);
    }
    
    outputChannel.appendLine('\n--- End ---');
    
    if (config.showCostInResponse) {
      // Note: Cost info would come from response metadata in production
      outputChannel.appendLine('\n(Cost info would be displayed here)');
    }
    
  } catch (error) {
    outputChannel.appendLine(`\nError: ${error}`);
    vscode.window.showErrorMessage(`ModelMesh error: ${error}`);
  }
}