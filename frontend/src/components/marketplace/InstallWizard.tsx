import React, { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { AlertCircle, CheckCircle2, Loader2, RotateCcw } from 'lucide-react';

export interface InstallWizardProps {
  skillId: string;
  skillName: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: (skillId: string) => void;
  onStartInstall: (skillId: string) => Promise<{ job_id: string }>;
  onPollProgress: (jobId: string) => Promise<{
    status: 'downloading' | 'validating' | 'extracting' | 'checking' | 'finalizing' | 'success' | 'failed';
    current_step: number;
    progress: number;
    step_messages: Record<string, string>;
    error?: string;
    failed_step?: number;
    can_retry?: boolean;
  }>;
}

const STEPS = [
  { name: 'Download', icon: '📥' },
  { name: 'Validate', icon: '✓' },
  { name: 'Extract', icon: '📦' },
  { name: 'Health Check', icon: '🏥' },
  { name: 'Finalize', icon: '✨' },
];

export function InstallWizard({
  skillId,
  skillName,
  isOpen,
  onClose,
  onSuccess,
  onStartInstall,
  onPollProgress,
}: InstallWizardProps) {
  const [status, setStatus] = useState<'idle' | 'installing' | 'success' | 'failed'>('idle');
  const [currentStep, setCurrentStep] = useState(0);
  const [progress, setProgress] = useState(0);
  const [stepMessages, setStepMessages] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [failedStep, setFailedStep] = useState<number | null>(null);
  const [canRetry, setCanRetry] = useState(false);

  // Start install
  const handleStartInstall = async () => {
    try {
      setStatus('installing');
      setCurrentStep(0);
      setProgress(0);
      setError(null);
      setFailedStep(null);

      const result = await onStartInstall(skillId);
      setJobId(result.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start install');
      setStatus('failed');
    }
  };

  // Poll progress
  useEffect(() => {
    if (status !== 'installing' || !jobId) return;

    const pollInterval = setInterval(async () => {
      try {
        const data = await onPollProgress(jobId);
        setCurrentStep(data.current_step);
        setProgress(data.progress);
        setStepMessages(data.step_messages);

        if (data.status === 'success') {
          setStatus('success');
          setProgress(100);
          onSuccess(skillId);
          clearInterval(pollInterval);
        } else if (data.status === 'failed') {
          setStatus('failed');
          setError(data.error || 'Installation failed');
          setFailedStep(data.failed_step || 0);
          setCanRetry(data.can_retry || false);
          clearInterval(pollInterval);
        }
      } catch (err) {
        console.error('Poll error:', err);
        // Retry polling on error (could be transient)
      }
    }, 500);

    return () => clearInterval(pollInterval);
  }, [status, jobId, skillId, onSuccess, onPollProgress]);

  const handleRetry = () => {
    setFailedStep(null);
    setCanRetry(false);
    handleStartInstall();
  };

  const handleClose = () => {
    if (status === 'installing') return; // Prevent closing during install
    setStatus('idle');
    setJobId(null);
    setError(null);
    setFailedStep(null);
    onClose();
  };

  const handleFinish = () => {
    handleClose();
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Install {skillName}</DialogTitle>
          <DialogDescription>
            {status === 'idle' && 'Click "Install" to begin'}
            {status === 'installing' && 'Installing... this usually takes about 10 seconds'}
            {status === 'success' && 'Installation completed successfully!'}
            {status === 'failed' && 'Installation failed. You can retry or discard.'}
          </DialogDescription>
        </DialogHeader>

        {/* Progress Bar */}
        <div className="space-y-2 py-6">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Progress</span>
            <span className="text-sm text-gray-600">{progress}%</span>
          </div>
          <Progress value={progress} className="h-2" />
        </div>

        {/* Steps Timeline */}
        <div className="space-y-3 py-4">
          {STEPS.map((step, idx) => {
            const isCompleted = idx < currentStep || status === 'success';
            const isCurrent = idx === currentStep && status === 'installing';
            const isFailed = idx === failedStep && status === 'failed';

            return (
              <div key={idx} className="flex gap-3 items-start">
                {/* Step Indicator */}
                <div className="flex-shrink-0 mt-1">
                  {isCompleted && (
                    <CheckCircle2 className="h-5 w-5 text-green-600" />
                  )}
                  {isCurrent && (
                    <Loader2 className="h-5 w-5 text-blue-600 animate-spin" />
                  )}
                  {isFailed && (
                    <AlertCircle className="h-5 w-5 text-red-600" />
                  )}
                  {!isCompleted && !isCurrent && !isFailed && (
                    <div className="h-5 w-5 rounded-full border-2 border-gray-300 bg-gray-100" />
                  )}
                </div>

                {/* Step Info */}
                <div className="flex-1">
                  <p className={`font-semibold text-sm ${isCurrent ? 'text-blue-600' : isFailed ? 'text-red-600' : 'text-gray-900'}`}>
                    {step.name}
                  </p>
                  {stepMessages[idx.toString()] && (
                    <p className="text-xs text-gray-600 mt-1">
                      {stepMessages[idx.toString()]}
                    </p>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Error Message */}
        {error && status === 'failed' && (
          <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
            <p className="text-sm text-red-800 font-semibold">Error</p>
            <p className="text-sm text-red-700 mt-1">{error}</p>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-3 justify-end mt-6 pt-4 border-t">
          {status === 'idle' && (
            <>
              <Button variant="outline" onClick={handleClose}>
                Cancel
              </Button>
              <Button onClick={handleStartInstall}>
                Install
              </Button>
            </>
          )}

          {status === 'installing' && (
            <div className="text-sm text-gray-600 flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin" />
              Installing...
            </div>
          )}

          {status === 'success' && (
            <>
              <Button variant="outline" onClick={handleClose}>
                Install Another
              </Button>
              <Button onClick={handleFinish}>
                Finish
              </Button>
            </>
          )}

          {status === 'failed' && (
            <>
              <Button variant="outline" onClick={handleClose}>
                Discard
              </Button>
              {canRetry && (
                <Button onClick={handleRetry} className="gap-2">
                  <RotateCcw className="h-4 w-4" />
                  Retry
                </Button>
              )}
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
