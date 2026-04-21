import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';

export interface SkillCardProps {
  skillId: string;
  name: string;
  description: string;
  useCases: string[];
  languages: string[];
  complexity: string;
  trustLevel: string;
  isInstalled?: boolean;
  onSelect: (skillId: string) => void;
  onInstallClick: (skillId: string) => void;
}

const complexityColors: Record<string, string> = {
  beginner: 'bg-green-100 text-green-800',
  intermediate: 'bg-blue-100 text-blue-800',
  advanced: 'bg-purple-100 text-purple-800',
};

const trustLevelColors: Record<string, string> = {
  verified: 'bg-emerald-50 border-emerald-200',
  community: 'bg-amber-50 border-amber-200',
  experimental: 'bg-rose-50 border-rose-200',
};

const trustLevelBadgeColors: Record<string, string> = {
  verified: 'bg-emerald-100 text-emerald-800',
  community: 'bg-amber-100 text-amber-800',
  experimental: 'bg-rose-100 text-rose-800',
};

export function SkillCard({
  skillId,
  name,
  description,
  useCases,
  languages,
  complexity,
  trustLevel,
  isInstalled = false,
  onSelect,
  onInstallClick,
}: SkillCardProps) {
  const handleCardClick = () => {
    onSelect(skillId);
  };

  const handleInstallClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onInstallClick(skillId);
  };

  return (
    <Card 
      className={`cursor-pointer hover:shadow-lg transition-shadow border ${trustLevelColors[trustLevel] || 'bg-gray-50'}`}
      onClick={handleCardClick}
    >
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1">
            <CardTitle className="text-lg">{name}</CardTitle>
            <CardDescription className="text-sm mt-1">
              {description.substring(0, 80)}
              {description.length > 80 ? '...' : ''}
            </CardDescription>
          </div>
          {isInstalled && (
            <Badge variant="secondary" className="bg-green-100 text-green-800">
              Installed
            </Badge>
          )}
        </div>
      </CardHeader>
      
      <CardContent className="pb-3">
        <div className="space-y-3">
          {/* Complexity Badge */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-600">Complexity:</span>
            <Badge className={complexityColors[complexity] || 'bg-gray-100'}>
              {complexity}
            </Badge>
          </div>

          {/* Languages */}
          {languages.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {languages.slice(0, 3).map((lang) => (
                <Badge key={lang} variant="outline" className="text-xs">
                  {lang}
                </Badge>
              ))}
              {languages.length > 3 && (
                <Badge variant="outline" className="text-xs">
                  +{languages.length - 3}
                </Badge>
              )}
            </div>
          )}

          {/* Use Cases (chips) */}
          {useCases.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {useCases.slice(0, 2).map((uc) => (
                <Badge key={uc} variant="secondary" className="text-xs bg-slate-100">
                  {uc}
                </Badge>
              ))}
              {useCases.length > 2 && (
                <Badge variant="secondary" className="text-xs bg-slate-100">
                  +{useCases.length - 2}
                </Badge>
              )}
            </div>
          )}

          {/* Trust Level */}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-600">Trust:</span>
            <Badge className={trustLevelBadgeColors[trustLevel] || 'bg-gray-100'}>
              {trustLevel}
            </Badge>
          </div>
        </div>
      </CardContent>

      <CardFooter>
        <Button
          onClick={handleInstallClick}
          disabled={isInstalled}
          variant={isInstalled ? "outline" : "default"}
          size="sm"
          className="w-full"
        >
          {isInstalled ? 'Installed' : 'View Details'}
        </Button>
      </CardFooter>
    </Card>
  );
}
