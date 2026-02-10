import { api_host } from '@/utils/api';
import classNames from 'classnames';
import { ImageOff } from 'lucide-react';
import React, { useCallback, useState } from 'react';
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover';

interface IImage extends React.ImgHTMLAttributes<HTMLImageElement> {
  id: string;
  t?: string | number;
  label?: string;
}

const Image = ({ id, t, label, className, ...props }: IImage) => {
  const [hasError, setHasError] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const handleError = useCallback(() => {
    setHasError(true);
    setIsLoading(false);
  }, []);

  const handleLoad = useCallback(() => {
    setIsLoading(false);
  }, []);

  if (hasError) {
    return (
      <div
        className={classNames(
          'flex items-center justify-center bg-bg-card rounded text-text-secondary',
          className,
        )}
        style={{ minWidth: 60, minHeight: 60 }}
      >
        <ImageOff className="size-5" />
      </div>
    );
  }

  const imageElement = (
    <img
      {...props}
      src={`${api_host}/document/image/${id}${t ? `?_t=${t}` : ''}`}
      className={classNames(
        'max-w-[45vw] max-h-[40wh] block',
        { 'animate-pulse bg-bg-card': isLoading },
        className,
      )}
      onError={handleError}
      onLoad={handleLoad}
    />
  );

  if (!label) {
    return imageElement;
  }

  return (
    <div className="relative inline-block w-full">
      {imageElement}
      <div className="absolute bottom-2 right-2 bg-accent-primary text-white px-2 py-0.5 rounded-xl text-xs font-normal backdrop-blur-sm">
        {label}
      </div>
    </div>
  );
};

export default Image;

export const ImageWithPopover = ({ id }: { id: string }) => {
  return (
    <Popover>
      <PopoverTrigger>
        <Image id={id} className="max-h-[100px] inline-block"></Image>
      </PopoverTrigger>
      <PopoverContent>
        <Image id={id} className="max-w-[100px] object-contain"></Image>
      </PopoverContent>
    </Popover>
  );
};
