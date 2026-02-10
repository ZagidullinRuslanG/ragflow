'use client';

import { SwitchFormField } from '@/components/switch-fom-field';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { useTranslate } from '@/hooks/common-hooks';
import { useFormContext } from 'react-hook-form';

export function ChatAcyclicSettings() {
  const { t } = useTranslate('chat');
  const form = useFormContext();

  return (
    <div className="space-y-6">
      <h4 className="text-sm font-medium">
        {t('acyclicClientSettings', 'Acyclic Client Settings')}
      </h4>

      <SwitchFormField
        name="show_thinking"
        label={t('showThinking')}
        tooltip={t('showThinkingTip')}
      />

      <SwitchFormField
        name="show_retries"
        label={t('showRetries')}
        tooltip={t('showRetriesTip')}
      />

      <FormField
        control={form.control}
        name="model_context_const_size"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('modelContextConstSizeTip')}>
              {t('modelContextConstSize')}
            </FormLabel>
            <FormControl>
              <Input type="number" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="retries_count"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('retriesCountTip')}>
              {t('retriesCount')}
            </FormLabel>
            <FormControl>
              <Input type="number" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="retry_temp_shift"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('retryTempShiftTip')}>
              {t('retryTempShift')}
            </FormLabel>
            <FormControl>
              <Input placeholder="0.1, 0.2, 0.3" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="retry_timeout_shift"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('retryTimeoutShiftTip')}>
              {t('retryTimeoutShift')}
            </FormLabel>
            <FormControl>
              <Input placeholder="0, 0.1, 0.2" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="loop_min_chars"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('loopMinCharsTip')}>
              {t('loopMinChars')}
            </FormLabel>
            <FormControl>
              <Input type="number" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="loop_thresh"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('loopThreshTip')}>
              {t('loopThresh')}
            </FormLabel>
            <FormControl>
              <Input type="number" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="check_every_n"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('checkEveryNTip')}>
              {t('checkEveryN')}
            </FormLabel>
            <FormControl>
              <Input type="number" {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="prompt_suffix_on_retry"
        render={({ field }) => (
          <FormItem>
            <FormLabel tooltip={t('promptSuffixOnRetryTip')}>
              {t('promptSuffixOnRetry')}
            </FormLabel>
            <FormControl>
              <Textarea {...field} />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
