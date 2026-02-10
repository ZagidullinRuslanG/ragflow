import { useTranslate } from '@/hooks/common-hooks';
import { useFormContext } from 'react-hook-form';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from './ui/form';
import { Input } from './ui/input';

export function TaskPageSizeFormField() {
  const { t } = useTranslate('knowledgeDetails');
  const form = useFormContext();

  return (
    <FormField
      control={form.control}
      name="parser_config.task_page_size"
      render={({ field }) => (
        <FormItem className="items-center space-y-0">
          <div className="flex items-center">
            <FormLabel
              tooltip={t('taskPageSizeTip')}
              className="text-sm whitespace-wrap w-1/4"
            >
              {t('taskPageSize')}
            </FormLabel>
            <div className="w-3/4">
              <FormControl>
                <Input {...field} type="number" min={1} max={128} />
              </FormControl>
            </div>
          </div>
          <div className="flex pt-1">
            <div className="w-1/4"></div>
            <FormMessage />
          </div>
        </FormItem>
      )}
    />
  );
}
