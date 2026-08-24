import React, { useLayoutEffect, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import './styles.css';

gsap.registerPlugin(ScrollTrigger);

const projects = [
  { no: '01', title: 'Mother’s Day Film', type: 'Film / Social', image: 'https://images.unsplash.com/photo-1511895426328-dc8714191300?auto=format&fit=crop&w=1800&q=85' },
  { no: '02', title: 'iD Fresh — 16 Layers', type: 'Campaign / 360', image: 'https://images.unsplash.com/photo-1601050690597-df0568f70950?auto=format&fit=crop&w=1800&q=85' },
  { no: '03', title: 'Trust Factory', type: 'Digital / Experience', image: 'https://images.unsplash.com/photo-1581094794329-c8112a89af12?auto=format&fit=crop&w=1800&q=85' },
  { no: '04', title: 'Ready Mix', type: 'Brand / Packaging', image: 'https://images.unsplash.com/photo-1556910103-1c02745aae4d?auto=format&fit=crop&w=1800&q=85' },
  { no: '05', title: 'Dream Team', type: 'Experience / Event', image: 'https://images.unsplash.com/photo-1505373877841-8d25f7d46678?auto=format&fit=crop&w=1800&q=85' }
];

function App() {
  const root = useRef(null);
  const horizontal = useRef(null);

  useLayoutEffect(() => {
    const lenis = new Lenis({ duration: 1.15, smoothWheel: true, smoothTouch: false });
    const raf = (time) => { lenis.raf(time); requestAnimationFrame(raf); };
    requestAnimationFrame(raf);

    const ctx = gsap.context(() => {
      gsap.to('.hero-copy', {
        scale: 1.55, opacity: 0, yPercent: -20, ease: 'none',
        scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true }
      });
      gsap.to('.hero-media', {
        scale: 1.12, ease: 'none',
        scrollTrigger: { trigger: '.hero', start: 'top top', end: 'bottom top', scrub: true }
      });

      const aboutTl = gsap.timeline({
        scrollTrigger: { trigger: '.about', start: 'top top', end: '+=1500', pin: true, scrub: 1 }
      });
      aboutTl.from('.about-kicker', { x: -100, opacity: 0, duration: .6 })
        .from('.about-title', { y: 100, opacity: 0, duration: .8 }, '<.15')
        .from('.about-copy', { x: 120, opacity: 0, duration: .8 }, '<.2')
        .from('.stat', { x: 120, opacity: 0, stagger: .12, duration: .45 }, '<.15')
        .to('.about-orb', { scale: 2.2, rotate: 180, duration: 1.2 }, '<');

      const track = horizontal.current;
      const getDistance = () => Math.max(0, track.scrollWidth - window.innerWidth);
      gsap.to(track, {
        x: () => -getDistance(), ease: 'none',
        scrollTrigger: { trigger: '.work', start: 'top top', end: () => `+=${getDistance() + window.innerHeight}`, pin: true, scrub: 1, invalidateOnRefresh: true }
      });

      gsap.utils.toArray('.project-card').forEach((card) => {
        gsap.from(card.querySelector('.project-image'), {
          scale: 1.18, ease: 'none',
          scrollTrigger: { trigger: card, containerAnimation: undefined, start: 'left right', end: 'right left', scrub: true }
        });
      });

      gsap.from('.contact-title', {
        y: 100, opacity: 0,
        scrollTrigger: { trigger: '.contact', start: 'top 75%', end: 'top 35%', scrub: true }
      });
    }, root);

    return () => { ctx.revert(); lenis.destroy(); };
  }, []);

  return (
    <main ref={root}>
      <header className="nav">
        <a href="#top" className="logo">JK<span>®</span></a>
        <div className="nav-right"><span>Creative / Design / AI</span><a href="#contact">Let’s talk ↗</a></div>
      </header>

      <section className="hero" id="top">
        <div className="hero-media" />
        <div className="hero-overlay" />
        <div className="hero-copy">
          <p className="eyebrow">CREATIVE ASSOCIATE DIRECTOR · BANGALORE</p>
          <h1>Ideas<br /><em>in motion.</em></h1>
          <p className="hero-sub">I build brands, visual worlds and experiences that people remember.</p>
        </div>
        <div className="scroll-cue"><span>Scroll to enter</span><i /></div>
      </section>

      <section className="about">
        <div className="about-orb" />
        <div className="about-inner">
          <div className="about-kicker">01 — THE HUMAN</div>
          <h2 className="about-title">Design is not<br /><em>decoration.</em></h2>
          <div className="about-copy"><p>It is the way an idea becomes impossible to ignore.</p><p>I’m JK — a designer, creative leader and AI obsessive building across branding, packaging, film, digital, events and experiences.</p></div>
          <div className="stats">
            <div className="stat"><strong>15+</strong><span>Years creating</span></div>
            <div className="stat"><strong>28+</strong><span>People mentored</span></div>
            <div className="stat"><strong>360°</strong><span>Creative thinking</span></div>
          </div>
        </div>
      </section>

      <section className="work">
        <div className="work-track" ref={horizontal}>
          <div className="work-intro"><span>02 — THE WORK</span><h2>Selected<br /><em>frames.</em></h2><p>Scroll through the work.<br />Each project is a different story.</p></div>
          {projects.map((project) => (
            <article className="project-card" key={project.no}>
              <div className="project-image-wrap"><img className="project-image" src={project.image} alt="" /></div>
              <div className="project-meta"><span>{project.no} / 05</span><div><h3>{project.title}</h3><p>{project.type}</p></div><span>View ↗</span></div>
            </article>
          ))}
          <div className="work-end"><span>END OF REEL</span><strong>More stories<br />coming soon.</strong></div>
        </div>
      </section>

      <section className="principles">
        <span>03 — THE APPROACH</span>
        <div className="principle-list">
          <div><b>01</b><h3>Think<br /><em>different.</em></h3></div>
          <div><b>02</b><h3>Make it<br /><em>matter.</em></h3></div>
          <div><b>03</b><h3>Move<br /><em>people.</em></h3></div>
        </div>
      </section>

      <section className="contact" id="contact">
        <span>04 — THE END FRAME</span>
        <h2 className="contact-title">Have an idea?<br /><em>Let’s make it move.</em></h2>
        <a className="contact-link" href="mailto:jaspalrocks21@gmail.com">jaspalrocks21@gmail.com ↗</a>
        <footer><span>JK® / 2026</span><span>Instagram · LinkedIn · YouTube</span><span>Built for the scroll.</span></footer>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')).render(<App />);
