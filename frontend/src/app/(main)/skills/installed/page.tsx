'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { useInstalledSkills } from '@/hooks/useInstalledSkills';
import { useToast } from '@/app/ToastProvider';
import { API_BASE, AUTH_HEADERS } from '@/lib/config';

function formatInstalledDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return 'Unknown';
  }

  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

const healthStyles: Record<string, string> = {
  healthy: 'bg-emerald-100 text-emerald-800',
  warning: 'bg-amber-100 text-amber-800',
  unknown: 'bg-slate-100 text-slate-700',
};

export default function InstalledSkillsPage() {
  const { addToast } = useToast();
  const {
    hydrated,
    installedSkills,
    mergeInstalledSkills,
    removeInstalledSkill,
    toggleSkillEnabled,
  } = useInstalledSkills();

  useEffect(() => {
    const loadInstalled = async () => {
      try {
        const response = await fetch(`${API_BASE}/v1/skills/installed`, {
          headers: AUTH_HEADERS,
        });
        if (!response.ok) {
          return;
        }

        const payload = await response.json();
        if (Array.isArray(payload) && payload.length > 0) {
          mergeInstalledSkills(payload);
        }
      } catch {
        // Keep local state available if backend is unavailable.
      }
    };

    loadInstalled();
  }, [mergeInstalledSkills]);

  const handleRemove = async (skillId: string, skillName: string) => {
    try {
      const response = await fetch(`${API_BASE}/v1/skills/${skillId}/remove`, {
        method: 'POST',
        headers: AUTH_HEADERS,
      });
      if (!response.ok) {
        throw new Error('Failed to remove skill');
      }
    } catch {
      addToast({
        type: 'error',
        title: 'Remove failed',
        message: `Could not remove ${skillName} from backend state.`,
        autoClose: 3000,
      });
      return;
    }

    removeInstalledSkill(skillId);
    addToast({
      type: 'info',
      title: 'Skill removed',
      message: `${skillName} was removed from your installed skills.`,
      autoClose: 3000,
    });
  };

  const handleToggle = async (skillId: string, skillName: string, enabled: boolean) => {
    try {
      const response = await fetch(`${API_BASE}/v1/skills/${skillId}/toggle`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify({ enabled: !enabled }),
      });
      if (!response.ok) {
        throw new Error('Failed to update skill state');
      }
    } catch {
      addToast({
        type: 'error',
        title: 'Toggle failed',
        message: `Could not update ${skillName} state in backend.`,
        autoClose: 3000,
      });
      return;
    }

    toggleSkillEnabled(skillId);
    addToast({
      type: 'success',
      title: enabled ? 'Skill disabled' : 'Skill enabled',
      message: `${skillName} is now ${enabled ? 'disabled' : 'enabled'}.`,
      autoClose: 2500,
    });
  };

  if (!hydrated) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6">
        <div className="max-w-6xl mx-auto">
          <Card className="p-8">
            <p className="text-sm text-gray-600">Loading installed skills...</p>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6">
      <div className="max-w-6xl mx-auto space-y-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <h1 className="text-4xl font-bold text-slate-900">Installed Skills</h1>
            <p className="text-gray-600 mt-2">
              Manage the skills you have added locally from the marketplace.
            </p>
          </div>
          <Link href="/marketplace">
            <Button variant="outline">Browse Marketplace</Button>
          </Link>
        </div>

        {installedSkills.length === 0 ? (
          <Card className="p-10 text-center">
            <CardTitle className="mb-2 text-2xl">No installed skills yet</CardTitle>
            <CardDescription className="mb-6">
              Install a skill from the marketplace to manage it here.
            </CardDescription>
            <div>
              <Link href="/marketplace">
                <Button>Open Marketplace</Button>
              </Link>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {installedSkills.map((skill) => (
              <Card key={skill.skill_id} className="border-slate-200 shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <CardTitle className="text-xl">{skill.name}</CardTitle>
                      <CardDescription className="mt-1">
                        {skill.description || 'No description provided.'}
                      </CardDescription>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Badge className={healthStyles[skill.health_status] || healthStyles.unknown}>
                        {skill.health_status}
                      </Badge>
                      <Badge variant="outline">v{skill.version}</Badge>
                      <Badge variant="secondary" className={skill.enabled ? 'bg-blue-100 text-blue-800' : 'bg-slate-200 text-slate-700'}>
                        {skill.enabled ? 'enabled' : 'disabled'}
                      </Badge>
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid grid-cols-1 gap-3 text-sm text-gray-600 md:grid-cols-4">
                    <div>
                      <p className="font-semibold text-slate-900">Installed</p>
                      <p>{formatInstalledDate(skill.installed_at)}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-slate-900">Complexity</p>
                      <p className="capitalize">{skill.complexity}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-slate-900">Trust</p>
                      <p className="capitalize">{skill.trust_level}</p>
                    </div>
                    <div>
                      <p className="font-semibold text-slate-900">Languages</p>
                      <p>{skill.languages.length > 0 ? skill.languages.join(', ') : 'Any'}</p>
                    </div>
                  </div>

                  {skill.use_cases.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {skill.use_cases.map((useCase) => (
                        <Badge key={useCase} variant="secondary" className="bg-slate-100 text-slate-700">
                          {useCase}
                        </Badge>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex flex-wrap gap-3 text-sm">
                      {skill.install_url && (
                        <a href={skill.install_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                          View Source
                        </a>
                      )}
                      {skill.manifest_url && (
                        <a href={skill.manifest_url} target="_blank" rel="noreferrer" className="text-blue-600 hover:underline">
                          View Manifest
                        </a>
                      )}
                    </div>
                    <div className="flex gap-3">
                      <Button variant="outline" onClick={() => handleToggle(skill.skill_id, skill.name, skill.enabled)}>
                        {skill.enabled ? 'Disable' : 'Enable'}
                      </Button>
                      <Button
                        variant="outline"
                        onClick={() => handleRemove(skill.skill_id, skill.name)}
                        className="border-red-200 text-red-700 hover:bg-red-50 hover:text-red-800"
                      >
                        Remove
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}