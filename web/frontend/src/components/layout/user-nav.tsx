'use client';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';

export function UserNav() {
  return (
    <Button variant='ghost' className='relative h-8 w-8 rounded-full'>
      <Avatar className='h-8 w-8'>
        <AvatarFallback>NFL</AvatarFallback>
      </Avatar>
    </Button>
  );
}
