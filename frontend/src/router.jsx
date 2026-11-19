import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';

const RouterContext = createContext({
  path: '/',
  pathname: '/',
  search: '',
  navigate: () => {},
});

export function RouterProvider({ children }) {
  const [currentUrl, setCurrentUrl] = useState(() => {
    if (typeof window !== 'undefined') {
      return (window.location.pathname || '/') + (window.location.search || '');
    }
    return '/';
  });

  useEffect(() => {
    const onPopState = () => {
      setCurrentUrl((window.location.pathname || '/') + (window.location.search || ''));
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const navigate = useCallback((to, replace = false) => {
    const current = (window.location.pathname || '/') + (window.location.search || '');
    if (to === current) return;
    if (replace) {
      window.history.replaceState({}, '', to);
    } else {
      window.history.pushState({}, '', to);
    }
    setCurrentUrl(to);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  const [pathname, search] = currentUrl.split('?');

  return (
    <RouterContext.Provider value={{ path: currentUrl, pathname: pathname || '/', search: search ? `?${search}` : '', navigate }}>
      {children}
    </RouterContext.Provider>
  );
}

export function useRouter() {
  return useContext(RouterContext);
}

export function Link({ href, children, className = '', onClick, ...props }) {
  const { navigate } = useRouter();

  const handleClick = (e) => {
    if (onClick) onClick(e);
    // Don't intercept if modifier keys pressed or default prevented
    if (
      !e.defaultPrevented &&
      e.button === 0 &&
      !e.metaKey &&
      !e.ctrlKey &&
      !e.altKey &&
      !e.shiftKey &&
      href.startsWith('/')
    ) {
      e.preventDefault();
      navigate(href);
    }
  };

  return (
    <a href={href} className={className} onClick={handleClick} {...props}>
      {children}
    </a>
  );
}
