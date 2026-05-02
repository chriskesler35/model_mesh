import React from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

interface RemoveSkillModalProps {
  isOpen: boolean;
  skillName: string;
  onClose: () => void;
  onConfirm: () => void;
}

export function RemoveSkillModal({
  isOpen,
  skillName,
  onClose,
  onConfirm,
}: RemoveSkillModalProps) {
  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Remove {skillName}?</DialogTitle>
          <DialogDescription>
            This removes the skill from your local installed-skills list. You can reinstall it later from the marketplace.
          </DialogDescription>
        </DialogHeader>

        <div className="flex justify-end gap-3 pt-4">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={onConfirm} className="bg-red-600 hover:bg-red-700 text-white">
            Remove Skill
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}