import { FormContainer } from '@/components/form-container';
import { KnowledgeBaseFormField } from '@/components/knowledge-base-item';
import { Form } from '@/components/ui/form';
import { zodResolver } from '@hookform/resolvers/zod';
import { memo } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import { initialAnswer2Values } from '../../constant';
import { useFormValues } from '../../hooks/use-form-values';
import { useWatchFormChange } from '../../hooks/use-watch-form-change';
import { INextOperatorForm } from '../../interface';
import { buildOutputList } from '../../utils/build-output-list';
import { FormWrapper } from '../components/form-wrapper';
import { Output } from '../components/output';

const FormSchema = z.object({
  kb_ids: z.array(z.string()),
});

const outputList = buildOutputList(initialAnswer2Values.outputs);

function Answer2Form({ node }: INextOperatorForm) {
  const defaultValues = useFormValues(initialAnswer2Values, node);

  const form = useForm<z.infer<typeof FormSchema>>({
    defaultValues,
    resolver: zodResolver(FormSchema),
  });

  useWatchFormChange(node?.id, form);

  return (
    <Form {...form}>
      <FormWrapper>
        <FormContainer>
          <KnowledgeBaseFormField />
        </FormContainer>
      </FormWrapper>
      <div className="p-5">
        <Output list={outputList} />
      </div>
    </Form>
  );
}

export default memo(Answer2Form);
