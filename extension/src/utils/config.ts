import * as vscode from 'vscode';

export interface Config {
  apiUrl: string;
  apiKey: string;
  defaultPersona: string;
  streamResponses: boolean;
  showCostInResponse: boolean;
}

export function getConfig(): Config {
  const config = vscode.workspace.getConfiguration('modelmesh');
  
  return {
    apiUrl: config.get<string>('apiUrl') || 'http://localhost:18800/v1',
    apiKey: config.get<string>('apiKey') || 'modelmesh_local_dev_key',
    defaultPersona: config.get<string>('defaultPersona') || 'quick-helper',
    streamResponses: config.get<boolean>('streamResponses') ?? true,
    showCostInResponse: config.get<boolean>('showCostInResponse') ?? true,
  };
}