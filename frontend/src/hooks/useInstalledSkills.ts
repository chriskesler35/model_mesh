'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

const STORAGE_KEY = 'devforgeai:installed-skills';

export interface InstalledSkill {
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
  installed_at: string;
  health_status: 'healthy' | 'warning' | 'unknown';
  enabled: boolean;
}

export interface InstalledSkillInput {
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

function normalizeInstalledSkill(skill: Partial<InstalledSkill> & { skill_id: string }): InstalledSkill {
  return {
    skill_id: skill.skill_id,
    name: skill.name || skill.skill_id,
    description: skill.description || '',
    version: skill.version || 'unknown',
    use_cases: skill.use_cases || [],
    languages: skill.languages || [],
    complexity: skill.complexity || 'unknown',
    trust_level: skill.trust_level || 'community',
    install_url: skill.install_url || '',
    manifest_url: skill.manifest_url || '',
    installed_at: skill.installed_at || new Date().toISOString(),
    health_status: skill.health_status || 'healthy',
    enabled: skill.enabled ?? true,
  };
}

function readInstalledSkills(): InstalledSkill[] {
  if (typeof window === 'undefined') {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .filter((item): item is Partial<InstalledSkill> & { skill_id: string } => !!item?.skill_id)
      .map(normalizeInstalledSkill);
  } catch {
    return [];
  }
}

export function useInstalledSkills() {
  const [installedSkills, setInstalledSkills] = useState<InstalledSkill[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setInstalledSkills(readInstalledSkills());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated || typeof window === 'undefined') {
      return;
    }

    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(installedSkills));
  }, [hydrated, installedSkills]);

  const installedSkillIds = useMemo(
    () => installedSkills.map((skill) => skill.skill_id),
    [installedSkills],
  );

  const addInstalledSkill = useCallback((skill: InstalledSkillInput) => {
    setInstalledSkills((current) => {
      const existing = current.find((entry) => entry.skill_id === skill.skill_id);
      if (existing) {
        return current.map((entry) =>
          entry.skill_id === skill.skill_id
            ? {
                ...entry,
                ...skill,
              }
            : entry,
        );
      }

      return [
        {
          ...skill,
          installed_at: new Date().toISOString(),
          health_status: 'healthy',
          enabled: true,
        },
        ...current,
      ];
    });
  }, []);

  const mergeInstalledSkills = useCallback((skills: Array<Partial<InstalledSkill> & { skill_id: string }>) => {
    if (skills.length === 0) {
      return;
    }

    setInstalledSkills((current) => {
      const merged = new Map(current.map((skill) => [skill.skill_id, skill]));

      for (const skill of skills) {
        const existing = merged.get(skill.skill_id);
        merged.set(
          skill.skill_id,
          normalizeInstalledSkill({
            ...existing,
            ...skill,
            skill_id: skill.skill_id,
          }),
        );
      }

      return Array.from(merged.values()).sort((left, right) =>
        right.installed_at.localeCompare(left.installed_at),
      );
    });
  }, []);

  const removeInstalledSkill = useCallback((skillId: string) => {
    setInstalledSkills((current) => current.filter((skill) => skill.skill_id !== skillId));
  }, []);

  const toggleSkillEnabled = useCallback((skillId: string) => {
    setInstalledSkills((current) =>
      current.map((skill) =>
        skill.skill_id === skillId
          ? {
              ...skill,
              enabled: !skill.enabled,
              health_status: !skill.enabled ? 'healthy' : 'unknown',
            }
          : skill,
      ),
    );
  }, []);

  return {
    hydrated,
    installedSkills,
    installedSkillIds,
    addInstalledSkill,
    mergeInstalledSkills,
    removeInstalledSkill,
    toggleSkillEnabled,
  };
}