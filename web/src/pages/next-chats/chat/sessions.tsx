import { ConfirmDeleteDialog } from '@/components/confirm-delete-dialog';
import { MoreButton } from '@/components/more-button';
import { RAGFlowAvatar } from '@/components/ragflow-avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { SearchInput } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useSetModalState } from '@/hooks/common-hooks';
import {
  useFetchDialog,
  useFetchExternalSessions,
  useGetChatSearchParams,
  useRemoveConversation,
} from '@/hooks/use-chat-request';
import { cn } from '@/lib/utils';
import { Check, PanelLeftClose, Plus, Trash2 } from 'lucide-react';
import { useCallback, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useHandleClickConversationCard } from '../hooks/use-click-card';
import { useSelectDerivedConversationList } from '../hooks/use-select-conversation-list';
import { ConversationDropdown } from './conversation-dropdown';

type SessionTab = 'internal' | 'external';

type SessionProps = Pick<
  ReturnType<typeof useHandleClickConversationCard>,
  'handleConversationCardClick'
>;
export function Sessions({ handleConversationCardClick }: SessionProps) {
  const { t } = useTranslation();
  const {
    list: conversationList,
    addTemporaryConversation,
    removeTemporaryConversation,
    handleInputChange,
    searchString,
  } = useSelectDerivedConversationList();
  const { data } = useFetchDialog();
  const { visible, switchVisible } = useSetModalState(true);
  const { removeConversation } = useRemoveConversation();

  const [activeTab, setActiveTab] = useState<SessionTab>('internal');

  // External sessions
  const {
    data: externalSessions,
    handleInputChange: handleExternalSearchChange,
    searchString: externalSearchString,
  } = useFetchExternalSessions();

  // Selection mode state
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // Toggle selection mode (click batch delete icon)
  const toggleSelectionMode = useCallback(() => {
    setSelectionMode(true);
    setSelectedIds(new Set());
  }, []);

  // Exit selection mode (click return icon)
  const exitSelectionMode = useCallback(() => {
    setSelectionMode(false);
    setSelectedIds(new Set());
  }, []);

  // Toggle single item selection
  const toggleSelection = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const newSet = new Set(prev);
      if (newSet.has(id)) {
        newSet.delete(id);
      } else {
        newSet.add(id);
      }
      return newSet;
    });
  }, []);

  // Toggle select all
  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (prev.size === conversationList.length) {
        return new Set();
      }
      return new Set(conversationList.map((x) => x.id));
    });
  }, [conversationList]);

  // Batch delete
  const handleBatchDelete = useCallback(async () => {
    if (selectedIds.size > 0) {
      await removeConversation(Array.from(selectedIds));
      exitSelectionMode();
    }
  }, [selectedIds, removeConversation, exitSelectionMode]);

  const selectedCount = useMemo(() => selectedIds.size, [selectedIds]);
  const allSelected = useMemo(
    () =>
      selectedCount === conversationList.length && conversationList.length > 0,
    [selectedCount, conversationList.length],
  );

  const handleCardClick = useCallback(
    (conversationId: string, isNew: boolean) => () => {
      if (selectionMode) {
        toggleSelection(conversationId);
      } else {
        handleConversationCardClick(conversationId, isNew);
      }
    },
    [handleConversationCardClick, selectionMode, toggleSelection],
  );

  const { conversationId } = useGetChatSearchParams();

  const handleTabChange = useCallback((value: string) => {
    setActiveTab(value as SessionTab);
    setSelectionMode(false);
    setSelectedIds(new Set());
  }, []);

  if (!visible) {
    return (
      <div className="p-5">
        <RAGFlowAvatar
          avatar={data.icon}
          name={data.name}
          className="size-8 cursor-pointer"
          onClick={switchVisible}
        ></RAGFlowAvatar>
      </div>
    );
  }

  const isInternal = activeTab === 'internal';
  const displayList = isInternal ? conversationList : externalSessions;

  return (
    <section className="p-5 w-[296px] flex flex-col">
      <section className="flex items-center text-base justify-between gap-2">
        <div className="flex gap-3 items-center min-w-0">
          <RAGFlowAvatar
            avatar={data.icon}
            name={data.name}
            className="size-8"
          ></RAGFlowAvatar>
          <span className="flex-1 truncate">{data.name}</span>
        </div>
        <PanelLeftClose
          className="cursor-pointer size-4"
          onClick={switchVisible}
        />
      </section>

      <div className="pt-6 pb-2">
        <Tabs value={activeTab} onValueChange={handleTabChange}>
          <TabsList className="w-full">
            <TabsTrigger value="internal" className="flex-1 text-xs">
              {t('chat.conversations')}
              <span className="ml-1 text-text-secondary">
                {conversationList.length}
              </span>
            </TabsTrigger>
            <TabsTrigger value="external" className="flex-1 text-xs">
              {t('chat.externalSessions', { defaultValue: 'External' })}
              <span className="ml-1 text-text-secondary">
                {externalSessions.length}
              </span>
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {isInternal && (
        <div className="flex justify-between items-center mb-4">
          <div className="flex items-center gap-3"></div>
          {selectionMode && selectedCount > 0 ? (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                onClick={exitSelectionMode}
              >
                <img src="/return2.png" alt="back" className="h-4 w-4" />
              </Button>
              <ConfirmDeleteDialog
                onOk={handleBatchDelete}
                title={t('chat.batchDeleteSessions')}
                content={{
                  title: t('chat.deleteSelectedConfirm', {
                    count: selectedCount,
                  }),
                }}
              >
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-6 text-state-error"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </ConfirmDeleteDialog>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                onClick={addTemporaryConversation}
              >
                <Plus className="h-4 w-4" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="size-6"
                onClick={selectionMode ? toggleSelectAll : toggleSelectionMode}
              >
                {selectionMode && allSelected ? (
                  <Check className="h-4 w-4" />
                ) : (
                  <img
                    src="/batch_delete2.png"
                    alt="batch delete"
                    className="h-4 w-4"
                  />
                )}
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="pb-4">
        <SearchInput
          onChange={isInternal ? handleInputChange : handleExternalSearchChange}
          value={isInternal ? searchString : externalSearchString}
        ></SearchInput>
      </div>
      <div className="space-y-4 flex-1 overflow-auto">
        {displayList.map((x) => (
          <Card
            key={x.id}
            onClick={isInternal ? handleCardClick(x.id, x.is_new) : undefined}
            className={cn('cursor-pointer bg-transparent relative', {
              'bg-bg-card': conversationId === x.id && !selectionMode,
              'cursor-default': !isInternal,
            })}
          >
            <CardContent className="px-3 py-2 flex justify-between items-center group gap-1">
              <div className="flex items-center gap-2 flex-1 min-w-0">
                {isInternal && selectionMode && (
                  <span
                    className="flex-shrink-0"
                    onClick={(e) => e.stopPropagation()}
                    onMouseDown={(e) => e.stopPropagation()}
                  >
                    <Checkbox
                      checked={selectedIds.has(x.id)}
                      onCheckedChange={() => toggleSelection(x.id)}
                    />
                  </span>
                )}
                <div className="flex flex-col flex-1 min-w-0">
                  <div className="truncate">{x.name}</div>
                  {!isInternal && x.user_name && (
                    <div className="text-xs text-text-secondary truncate">
                      {x.user_name}
                    </div>
                  )}
                </div>
              </div>
              {isInternal && !selectionMode && (
                <ConversationDropdown
                  conversation={x}
                  removeTemporaryConversation={removeTemporaryConversation}
                >
                  <MoreButton></MoreButton>
                </ConversationDropdown>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}
