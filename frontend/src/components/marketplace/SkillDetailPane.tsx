import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { X } from 'lucide-react';

export interface SkillDetailPaneProps {
  skillId: string;
  name: string;
  description: string;
  version: string;
  useCases: string[];
  languages: string[];
  complexity: string;
  trustLevel: string;
  installUrl: string;
  manifestUrl: string;
  isInstalled?: boolean;
  onClose: () => void;
  onInstallClick: () => void;
}

export function SkillDetailPane({
  skillId,
  name,
  description,
  version,
  useCases,
  languages,
  complexity,
  trustLevel,
  installUrl,
  manifestUrl,
  isInstalled = false,
  onClose,
  onInstallClick,
}: SkillDetailPaneProps) {
  return (
    <Card className="h-full flex flex-col">
      <CardHeader className="flex flex-row items-start justify-between space-y-0 pb-4">
        <div className="flex-1">
          <CardTitle>{name}</CardTitle>
          <CardDescription className="text-xs text-gray-500 mt-1">
            ID: {skillId} • v{version}
          </CardDescription>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          className="h-8 w-8 p-0"
        >
          <X className="h-4 w-4" />
        </Button>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto space-y-4">
        {/* Description */}
        <div>
          <h4 className="font-semibold text-sm mb-2">About</h4>
          <p className="text-sm text-gray-700">{description}</p>
        </div>

        {/* Key Metadata */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <h5 className="font-semibold text-xs text-gray-600 mb-1">Complexity</h5>
            <Badge>{complexity}</Badge>
          </div>
          <div>
            <h5 className="font-semibold text-xs text-gray-600 mb-1">Trust Level</h5>
            <Badge variant="outline">{trustLevel}</Badge>
          </div>
        </div>

        {/* Use Cases */}
        {useCases.length > 0 && (
          <div>
            <h4 className="font-semibold text-sm mb-2">Use Cases</h4>
            <div className="flex flex-wrap gap-2">
              {useCases.map((uc) => (
                <Badge key={uc} variant="secondary" className="text-xs">
                  {uc}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Languages */}
        {languages.length > 0 && (
          <div>
            <h4 className="font-semibold text-sm mb-2">Languages</h4>
            <div className="flex flex-wrap gap-2">
              {languages.map((lang) => (
                <Badge key={lang} variant="outline" className="text-xs">
                  {lang}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* Links */}
        <div className="pt-4 border-t space-y-2">
          <a
            href={installUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline block"
          >
            → View on GitHub/Source
          </a>
          {manifestUrl && (
            <a
              href={manifestUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-blue-600 hover:underline block"
            >
              → View Manifest
            </a>
          )}
        </div>

        {/* Phase 5 Note */}
        <div className="p-3 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800 mt-4">
          <strong>Phase 5 Note:</strong> Install functionality coming in Phase 6. For now, you can browse and review available skills.
        </div>
      </CardContent>

      <div className="border-t p-4 mt-4">
        <Button
          onClick={onInstallClick}
          disabled={isInstalled}
          variant={isInstalled ? "outline" : "default"}
          size="sm"
          className="w-full"
        >
          {isInstalled ? 'Already Installed' : 'Install (Coming in Phase 6)'}
        </Button>
      </div>
    </Card>
  );
}
