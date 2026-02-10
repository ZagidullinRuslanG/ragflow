import {
  ConfirmDeleteDialog,
  ConfirmDeleteDialogNode,
} from '@/components/confirm-delete-dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  useDeleteAgent,
  useUpdateAgentSetting,
} from '@/hooks/use-agent-request';
import { useFetchUserInfo } from '@/hooks/use-user-setting-request';
import { IFlow } from '@/interfaces/database/agent';
import { Lock, PenLine, Share2, Trash2 } from 'lucide-react';
import { MouseEventHandler, PropsWithChildren, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useRenameAgent } from './use-rename-agent';

export function AgentDropdown({
  children,
  showAgentRenameModal,
  agent: agent,
}: PropsWithChildren &
  Pick<ReturnType<typeof useRenameAgent>, 'showAgentRenameModal'> & {
    agent: IFlow;
  }) {
  const { t } = useTranslation();
  const { deleteAgent } = useDeleteAgent();
  const { updateAgentSetting } = useUpdateAgentSetting();
  const { data: userInfo } = useFetchUserInfo();
  const isOwner = agent.user_id === userInfo?.id;
  const isShared = agent.permission === 'team';

  const handleShowAgentRenameModal: MouseEventHandler<HTMLDivElement> =
    useCallback(
      (e) => {
        e.stopPropagation();
        showAgentRenameModal(agent);
      },
      [agent, showAgentRenameModal],
    );

  const handleDelete: MouseEventHandler<HTMLDivElement> = useCallback(() => {
    deleteAgent([agent.id]);
  }, [agent.id, deleteAgent]);

  const handleToggleShare: MouseEventHandler<HTMLDivElement> = useCallback(
    (e) => {
      e.stopPropagation();
      updateAgentSetting({
        id: agent.id,
        title: agent.title,
        permission: isShared ? 'me' : 'team',
      });
    },
    [agent.id, agent.title, isShared, updateAgentSetting],
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuItem onClick={handleShowAgentRenameModal}>
          {t('common.rename')} <PenLine />
        </DropdownMenuItem>
        {isOwner && (
          <DropdownMenuItem onClick={handleToggleShare}>
            {isShared ? (
              <>
                {t('common.makePrivate', 'Make private')} <Lock />
              </>
            ) : (
              <>
                {t('common.shareWithTeam', 'Share with team')} <Share2 />
              </>
            )}
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <ConfirmDeleteDialog
          onOk={handleDelete}
          title={t('deleteModal.delAgent')}
          content={{
            node: (
              <ConfirmDeleteDialogNode
                avatar={{ avatar: agent.avatar, name: agent.title }}
                name={agent.title}
              />
            ),
          }}
        >
          <DropdownMenuItem
            className="text-state-error"
            onSelect={(e) => {
              e.preventDefault();
            }}
            onClick={(e) => {
              e.stopPropagation();
            }}
          >
            {t('common.delete')} <Trash2 />
          </DropdownMenuItem>
        </ConfirmDeleteDialog>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
