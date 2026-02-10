import { useTranslate } from '@/hooks/common-hooks';
import { useFormContext } from 'react-hook-form';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from './ui/form';
import { Textarea } from './ui/textarea';

export function AdditionalParsingInfoFormField() {
  const { t } = useTranslate('knowledgeDetails');
  const form = useFormContext();

  return (
    <FormField
      control={form.control}
      name="parser_config.additional_parsing_info"
      render={({ field }) => (
        <FormItem className="items-center space-y-0">
          <div className="flex items-center">
            <FormLabel
              tooltip={t('additionalParsingInfoTip')}
              className="text-sm whitespace-wrap w-1/4"
            >
              {t('additionalParsingInfo')}
            </FormLabel>
            <div className="w-3/4">
              <FormControl>
                <Textarea
                  {...field}
                  placeholder={t('additionalParsingInfoInputField')}
                  className="resize-y min-h-[60px]"
                />
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
