import TimeRangePicker from '@/components/originui/time-range-picker';
import { SearchInput } from '@/components/ui/input';
import { RAGFlowPagination } from '@/components/ui/ragflow-pagination';
import { Spin } from '@/components/ui/spin';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { useFetchAllAgentSessions } from '@/hooks/use-agent-request';
import {
  IAgentLogMessage,
  IAgentLogResponse,
} from '@/interfaces/database/agent';
import { IReferenceObject } from '@/interfaces/database/chat';
import { useQueryClient } from '@tanstack/react-query';
import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { DateRange } from '../../components/originui/calendar/index';
import { AgentLogDetailModal } from './agent-log-detail-modal';

const getStartOfToday = (): Date => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  return today;
};

const getEndOfToday = (): Date => {
  const today = new Date();
  today.setHours(23, 59, 59, 999);
  return today;
};

export const AgentSessionsList: React.FC = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const init = {
    keywords: '',
    from_date: getStartOfToday(),
    to_date: getEndOfToday(),
    orderby: 'update_time',
    desc: true,
    page: 1,
    page_size: 10,
  };
  const [searchParams, setSearchParams] = useState(init);
  const columns = [
    {
      title: t('flow.agentName'),
      dataIndex: 'agent_title',
      key: 'agent_title',
    },
    {
      title: 'ID',
      dataIndex: 'id',
      key: 'id',
    },
    {
      title: t('flow.lastMessage'),
      dataIndex: 'title',
      key: 'title',
      render: (_text: string, record: IAgentLogResponse) => (
        <span className="truncate max-w-[300px] inline-block">
          {record?.message?.length ? record?.message[0]?.content : ''}
        </span>
      ),
    },
    {
      title: 'State',
      dataIndex: 'state',
      key: 'state',
      render: (_text: string, record: IAgentLogResponse) => (
        <div
          className="size-2 rounded-full"
          style={{ backgroundColor: record.errors ? 'red' : 'green' }}
        ></div>
      ),
    },
    {
      title: t('flow.turns'),
      dataIndex: 'round',
      key: 'round',
    },
    {
      title: 'Latest Date',
      dataIndex: 'update_date',
      key: 'update_date',
      sortable: true,
    },
    {
      title: 'Create Date',
      dataIndex: 'create_date',
      key: 'create_date',
      sortable: true,
    },
  ];

  const { data: logData, loading } = useFetchAllAgentSessions(searchParams);
  const { sessions: data, total } = logData || {};

  const [currentDate, setCurrentDate] = useState<DateRange>({
    from: searchParams.from_date,
    to: searchParams.to_date,
  });
  const [keywords, setKeywords] = useState(searchParams.keywords);

  const handleDateRangeChange = ({
    from: startDate,
    to: endDate,
  }: DateRange) => {
    setCurrentDate({ from: startDate, to: endDate });
  };

  const [pagination, setPagination] = useState<{
    current: number;
    pageSize: number;
    total: number;
  }>({
    current: 1,
    pageSize: 10,
    total: total ?? 0,
  });

  useEffect(() => {
    setPagination((pre) => ({
      ...pre,
      total: total ?? 0,
    }));
  }, [total]);

  const [sortConfig, setSortConfig] = useState<{
    orderby: string;
    desc: boolean;
  }>({ orderby: init.orderby, desc: init.desc });

  const handlePageChange = (current?: number, pageSize?: number) => {
    let page = current || 1;
    if (pagination.pageSize !== pageSize) {
      page = 1;
    }
    setPagination({
      ...pagination,
      current: page,
      pageSize: pageSize || 10,
    });
  };

  const handleSearch = () => {
    setSearchParams((pre) => ({
      ...pre,
      from_date: currentDate.from as Date,
      to_date: currentDate.to as Date,
      page: pagination.current,
      page_size: pagination.pageSize,
      orderby: sortConfig?.orderby || '',
      desc: sortConfig?.desc,
      keywords: keywords,
    }));
  };

  const handleClickSearch = () => {
    setPagination({ ...pagination, current: 1 });
    handleSearch();
    queryClient.invalidateQueries({
      queryKey: ['fetchAllAgentSessions'],
    });
  };

  useEffect(() => {
    handleSearch();
  }, [pagination.current, pagination.pageSize, sortConfig]);

  const handleSort = (key: string) => {
    let desc = false;
    if (sortConfig && sortConfig.orderby === key) {
      desc = !sortConfig.desc;
    }
    setSortConfig({ orderby: key, desc });
  };

  const handleReset = () => {
    setSearchParams(init);
    setKeywords(init.keywords);
    setCurrentDate({ from: init.from_date, to: init.to_date });
  };

  const [openModal, setOpenModal] = useState(false);
  const [modalData, setModalData] = useState<IAgentLogResponse>();
  const showLogDetail = (item: IAgentLogResponse) => {
    if (item?.round) {
      setModalData(item);
      setOpenModal(true);
    }
  };

  return (
    <div className="p-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-semibold mb-4">
          {t('flow.sessionsHistory')}
        </h2>
        <div className="flex justify-end space-x-2 mb-4 text-foreground">
          <div className="flex items-center space-x-2">
            <span>ID/Title</span>
            <SearchInput
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              className="w-32"
            />
          </div>
          <div className="flex items-center space-x-2">
            <span className="whitespace-nowrap">Latest Date</span>
            <TimeRangePicker
              onSelect={handleDateRangeChange}
              selectDateRange={currentDate}
            />
          </div>
          <button
            type="button"
            className="bg-foreground text-text-title-invert px-4 py-1 rounded"
            onClick={handleClickSearch}
          >
            Search
          </button>
          <button
            type="button"
            className="bg-transparent text-foreground px-4 py-1 rounded border"
            onClick={handleReset}
          >
            Reset
          </button>
        </div>
      </div>
      <div className="border rounded-md overflow-auto">
        <Table rootClassName="max-h-[calc(100vh-320px)]">
          <TableHeader className="sticky top-0 bg-background z-10 shadow-sm">
            <TableRow>
              {columns.map((column) => (
                <TableHead
                  key={column.dataIndex}
                  onClick={
                    column.sortable
                      ? () => handleSort(column.dataIndex)
                      : undefined
                  }
                  className={
                    column.sortable ? 'cursor-pointer hover:bg-muted/50' : ''
                  }
                >
                  <div className="flex items-center">
                    {column.title}
                    {column.sortable &&
                      sortConfig?.orderby === column.dataIndex && (
                        <span className="ml-1">
                          {sortConfig.desc ? '\u2193' : '\u2191'}
                        </span>
                      )}
                  </div>
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center"
                >
                  <Spin size="large">
                    <span className="sr-only">Loading...</span>
                  </Spin>
                </TableCell>
              </TableRow>
            )}
            {!loading &&
              data?.map((item) => (
                <TableRow
                  key={item.id}
                  className="cursor-pointer"
                  onClick={() => showLogDetail(item)}
                >
                  {columns.map((column) => (
                    <TableCell key={column.dataIndex}>
                      {column.render
                        ? column.render(
                            item[
                              column.dataIndex as keyof IAgentLogResponse
                            ] as string,
                            item,
                          )
                        : (item[
                            column.dataIndex as keyof IAgentLogResponse
                          ] as string)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            {!loading && (!data || data.length === 0) && (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-24 text-center"
                >
                  {t('flow.noSessions')}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <div className="flex justify-end mt-4 w-full">
        <RAGFlowPagination
          {...pagination}
          total={pagination.total}
          onChange={(page, pageSize) => handlePageChange(page, pageSize)}
        />
      </div>
      <AgentLogDetailModal
        isOpen={openModal}
        message={modalData?.message as IAgentLogMessage[]}
        reference={modalData?.reference as unknown as IReferenceObject}
        onClose={() => setOpenModal(false)}
      />
    </div>
  );
};
