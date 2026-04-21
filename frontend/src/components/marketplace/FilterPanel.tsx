import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export interface FilterPanelProps {
  useCases: string[];
  languages: string[];
  complexityLevels: string[];
  trustLevels: string[];
  
  selectedUseCases: string[];
  selectedLanguages: string[];
  selectedComplexity: string | null;
  selectedTrustLevel: string | null;
  
  onUseCasesChange: (values: string[]) => void;
  onLanguagesChange: (values: string[]) => void;
  onComplexityChange: (value: string | null) => void;
  onTrustLevelChange: (value: string | null) => void;
  onClearFilters: () => void;
}

export function FilterPanel({
  useCases,
  languages,
  complexityLevels,
  trustLevels,
  selectedUseCases,
  selectedLanguages,
  selectedComplexity,
  selectedTrustLevel,
  onUseCasesChange,
  onLanguagesChange,
  onComplexityChange,
  onTrustLevelChange,
  onClearFilters,
}: FilterPanelProps) {
  const hasActiveFilters = selectedUseCases.length > 0 
    || selectedLanguages.length > 0 
    || selectedComplexity 
    || selectedTrustLevel;

  const handleUseCaseToggle = (uc: string) => {
    const updated = selectedUseCases.includes(uc)
      ? selectedUseCases.filter(x => x !== uc)
      : [...selectedUseCases, uc];
    onUseCasesChange(updated);
  };

  const handleLanguageToggle = (lang: string) => {
    const updated = selectedLanguages.includes(lang)
      ? selectedLanguages.filter(x => x !== lang)
      : [...selectedLanguages, lang];
    onLanguagesChange(updated);
  };

  const handleComplexityChange = (level: string) => {
    onComplexityChange(selectedComplexity === level ? null : level);
  };

  const handleTrustLevelChange = (level: string) => {
    onTrustLevelChange(selectedTrustLevel === level ? null : level);
  };

  return (
    <Card className="sticky top-4">
      <CardHeader>
        <CardTitle className="text-lg">Filters</CardTitle>
        {hasActiveFilters && (
          <Button
            variant="outline"
            size="sm"
            onClick={onClearFilters}
            className="w-full mt-2"
          >
            Clear Filters
          </Button>
        )}
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Use Cases */}
        {useCases.length > 0 && (
          <div className="space-y-3">
            <h4 className="font-semibold text-sm">Use Cases</h4>
            <ScrollArea className="h-48">
              <div className="space-y-2 pr-4">
                {useCases.map((uc) => (
                  <div key={uc} className="flex items-center gap-2">
                    <Checkbox
                      id={`uc-${uc}`}
                      checked={selectedUseCases.includes(uc)}
                      onCheckedChange={() => handleUseCaseToggle(uc)}
                    />
                    <Label htmlFor={`uc-${uc}`} className="text-sm cursor-pointer">
                      {uc}
                    </Label>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Languages */}
        {languages.length > 0 && (
          <div className="space-y-3">
            <h4 className="font-semibold text-sm">Languages</h4>
            <ScrollArea className="h-40">
              <div className="space-y-2 pr-4">
                {languages.map((lang) => (
                  <div key={lang} className="flex items-center gap-2">
                    <Checkbox
                      id={`lang-${lang}`}
                      checked={selectedLanguages.includes(lang)}
                      onCheckedChange={() => handleLanguageToggle(lang)}
                    />
                    <Label htmlFor={`lang-${lang}`} className="text-sm cursor-pointer">
                      {lang}
                    </Label>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        )}

        {/* Complexity */}
        {complexityLevels.length > 0 && (
          <div className="space-y-3">
            <h4 className="font-semibold text-sm">Complexity</h4>
            <div className="space-y-2">
              {complexityLevels.map((level) => (
                <div key={level} className="flex items-center gap-2">
                  <Checkbox
                    id={`complexity-${level}`}
                    checked={selectedComplexity === level}
                    onCheckedChange={() => handleComplexityChange(level)}
                  />
                  <Label htmlFor={`complexity-${level}`} className="text-sm cursor-pointer">
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </Label>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Trust Level */}
        {trustLevels.length > 0 && (
          <div className="space-y-3">
            <h4 className="font-semibold text-sm">Trust Level</h4>
            <div className="space-y-2">
              {trustLevels.map((level) => (
                <div key={level} className="flex items-center gap-2">
                  <Checkbox
                    id={`trust-${level}`}
                    checked={selectedTrustLevel === level}
                    onCheckedChange={() => handleTrustLevelChange(level)}
                  />
                  <Label htmlFor={`trust-${level}`} className="text-sm cursor-pointer">
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </Label>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
