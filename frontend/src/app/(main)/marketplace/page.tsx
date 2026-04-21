'use client';

import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { SkillCard } from '@/components/marketplace/SkillCard';
import { FilterPanel } from '@/components/marketplace/FilterPanel';
import { SkillDetailPane } from '@/components/marketplace/SkillDetailPane';
import { Loader2, AlertCircle } from 'lucide-react';

interface Skill {
  skill_id: string;
  name: string;
  description: string;
  version: string;
  use_cases: string[];
  languages: string[];
  complexity: string;
  trust_level: string;
  install_url: string;
  manifest_url: string;
}

interface FilterOptions {
  use_cases: string[];
  languages: string[];
  complexity_levels: string[];
  trust_levels: string[];
}

const API_BASE = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:19001';

export default function MarketplacePage() {
  // State
  const [skills, setSkills] = useState<Skill[]>([]);
  const [filterOptions, setFilterOptions] = useState<FilterOptions | null>(null);
  const [installedSkills, setInstalledSkills] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Search & Filter
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedUseCases, setSelectedUseCases] = useState<string[]>([]);
  const [selectedLanguages, setSelectedLanguages] = useState<string[]>([]);
  const [selectedComplexity, setSelectedComplexity] = useState<string | null>(null);
  const [selectedTrustLevel, setSelectedTrustLevel] = useState<string | null>(null);

  // Detail View
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null);

  // Fetch filter options and skills
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        setError(null);

        // Fetch filter options
        const filterRes = await fetch(`${API_BASE}/v1/marketplace/filters`);
        if (!filterRes.ok) throw new Error('Failed to load filter options');
        const filters: FilterOptions = await filterRes.json();
        setFilterOptions(filters);

        // Fetch all skills (initial load)
        const skillRes = await fetch(`${API_BASE}/v1/marketplace/skills`);
        if (!skillRes.ok) throw new Error('Failed to load skills');
        const skillData = await skillRes.json();
        setSkills(skillData.results || []);

        // Fetch installed skills (currently empty in Phase 5)
        const installedRes = await fetch(`${API_BASE}/v1/skills/installed`);
        if (installedRes.ok) {
          const installed = await installedRes.json();
          setInstalledSkills(installed.map((s: any) => s.skill_id));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  // Fetch filtered results when search or filters change
  const fetchFilteredSkills = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (searchQuery) params.append('search_query', searchQuery);
      if (selectedUseCases.length > 0) params.append('use_cases', selectedUseCases.join(','));
      if (selectedLanguages.length > 0) params.append('languages', selectedLanguages.join(','));
      if (selectedComplexity) params.append('complexity', selectedComplexity);
      if (selectedTrustLevel) params.append('trust_level', selectedTrustLevel);

      const url = `${API_BASE}/v1/marketplace/skills${params.toString() ? '?' + params.toString() : ''}`;
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to search skills');
      const data = await res.json();
      setSkills(data.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Search failed');
    }
  }, [searchQuery, selectedUseCases, selectedLanguages, selectedComplexity, selectedTrustLevel]);

  // Debounced search
  const searchTimeoutRef = React.useRef<NodeJS.Timeout>();
  useEffect(() => {
    if (searchTimeoutRef.current) clearTimeout(searchTimeoutRef.current);
    searchTimeoutRef.current = setTimeout(fetchFilteredSkills, 300);
  }, [fetchFilteredSkills]);

  // Clear filters
  const handleClearFilters = () => {
    setSearchQuery('');
    setSelectedUseCases([]);
    setSelectedLanguages([]);
    setSelectedComplexity(null);
    setSelectedTrustLevel(null);
  };

  // Handle skill selection
  const handleSelectSkill = (skillId: string) => {
    const skill = skills.find(s => s.skill_id === skillId);
    if (skill) setSelectedSkill(skill);
  };

  // Handle install click
  const handleInstallClick = (skillId: string) => {
    // Phase 5: Just show a message
    alert(`Install for ${skillId} coming in Phase 6!`);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold mb-2">Skills & Tools Marketplace</h1>
          <p className="text-gray-600">Discover and install tools, frameworks, and methods to enhance your workflow.</p>
        </div>

        {/* Search Bar */}
        <div className="mb-6">
          <Input
            placeholder="Search skills by name or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="text-lg h-12 rounded-lg border-2"
          />
        </div>

        {/* Error State */}
        {error && (
          <Card className="mb-6 p-4 bg-red-50 border-red-200">
            <div className="flex gap-3 items-start">
              <AlertCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
              <div>
                <h3 className="font-semibold text-red-900">Error</h3>
                <p className="text-sm text-red-800">{error}</p>
              </div>
            </div>
          </Card>
        )}

        {/* Loading State */}
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
            <span className="ml-2 text-gray-600">Loading marketplace...</span>
          </div>
        )}

        {/* Main Content */}
        {!loading && (
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
            {/* Sidebar: Filters */}
            <div className="lg:col-span-1">
              {filterOptions && (
                <FilterPanel
                  useCases={filterOptions.use_cases}
                  languages={filterOptions.languages}
                  complexityLevels={filterOptions.complexity_levels}
                  trustLevels={filterOptions.trust_levels}
                  selectedUseCases={selectedUseCases}
                  selectedLanguages={selectedLanguages}
                  selectedComplexity={selectedComplexity}
                  selectedTrustLevel={selectedTrustLevel}
                  onUseCasesChange={setSelectedUseCases}
                  onLanguagesChange={setSelectedLanguages}
                  onComplexityChange={setSelectedComplexity}
                  onTrustLevelChange={setSelectedTrustLevel}
                  onClearFilters={handleClearFilters}
                />
              )}
            </div>

            {/* Main: Skills Grid + Detail View */}
            <div className="lg:col-span-3">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Skills Grid */}
                <div className="lg:col-span-1">
                  {skills.length === 0 ? (
                    <Card className="p-8 text-center">
                      <p className="text-gray-600">No skills found matching your filters.</p>
                    </Card>
                  ) : (
                    <div className="space-y-4">
                      <p className="text-sm text-gray-600 font-semibold">
                        {skills.length} {skills.length === 1 ? 'skill' : 'skills'} found
                      </p>
                      <div className="space-y-4">
                        {skills.map((skill) => (
                          <SkillCard
                            key={skill.skill_id}
                            skillId={skill.skill_id}
                            name={skill.name}
                            description={skill.description}
                            useCases={skill.use_cases}
                            languages={skill.languages}
                            complexity={skill.complexity}
                            trustLevel={skill.trust_level}
                            isInstalled={installedSkills.includes(skill.skill_id)}
                            onSelect={handleSelectSkill}
                            onInstallClick={handleInstallClick}
                          />
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Detail Pane */}
                <div className="lg:col-span-1">
                  {selectedSkill ? (
                    <SkillDetailPane
                      skillId={selectedSkill.skill_id}
                      name={selectedSkill.name}
                      description={selectedSkill.description}
                      version={selectedSkill.version}
                      useCases={selectedSkill.use_cases}
                      languages={selectedSkill.languages}
                      complexity={selectedSkill.complexity}
                      trustLevel={selectedSkill.trust_level}
                      installUrl={selectedSkill.install_url}
                      manifestUrl={selectedSkill.manifest_url}
                      isInstalled={installedSkills.includes(selectedSkill.skill_id)}
                      onClose={() => setSelectedSkill(null)}
                      onInstallClick={() => handleInstallClick(selectedSkill.skill_id)}
                    />
                  ) : (
                    <Card className="p-8 text-center h-full flex items-center justify-center bg-gray-50">
                      <p className="text-gray-600">Select a skill to view details</p>
                    </Card>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
