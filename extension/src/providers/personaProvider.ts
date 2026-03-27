import * as vscode from 'vscode';
import { ModelMeshClient } from '../api/client';

class PersonaItem extends vscode.TreeItem {
  constructor(public readonly persona: { id: string; name: string }) {
    super(persona.name, vscode.TreeItemCollapsibleState.None);
    this.contextValue = 'persona';
    this.id = persona.id;
  }
}

export class PersonaProvider implements vscode.TreeDataProvider<PersonaItem> {
  private _onDidChangeTreeData = new vscode.EventEmitter<PersonaItem | undefined | null>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  refresh(): void {
    this._onDidChangeTreeData.fire(null);
  }

  getTreeItem(element: PersonaItem): vscode.TreeItem {
    return element;
  }

  async getChildren(): Promise<PersonaItem[]> {
    try {
      const client = new ModelMeshClient();
      const personas = await client.getPersonas();
      return personas.map(p => new PersonaItem(p));
    } catch (error) {
      vscode.window.showErrorMessage(`Failed to load personas: ${error}`);
      return [];
    }
  }
}

let currentPersona: string | undefined;

export function getCurrentPersona(): string | undefined {
  return currentPersona;
}

export function setCurrentPersona(persona: string): void {
  currentPersona = persona;
}