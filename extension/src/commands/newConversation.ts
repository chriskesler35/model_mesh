import * as vscode from 'vscode';
import { ModelMeshClient } from '../api/client';

export async function newConversation() {
  const client = new ModelMeshClient();
  client.newConversation();
  
  vscode.window.showInformationMessage('ModelMesh: Started new conversation');
}